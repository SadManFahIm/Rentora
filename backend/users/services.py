"""Email-OTP two-factor authentication service.

Design notes (security first):

- The 6-digit code and the opaque challenge token are both stored as
  SHA-256 hashes only — a database leak never yields replayable codes.
- The code is delivered over email (console backend in dev, SMTP in
  production). We never return the code from any API endpoint.
- Each challenge allows a bounded number of attempts (5) before it locks,
  and expires after a short TTL (10 minutes). ``create_challenge`` first
  closes any other pending challenges for the user, so a stale challenge
  can never be used to bypass a newer login.
"""

import hashlib
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import OTPChallenge

__all__ = [
    "_mask_email",
    "_sha256",
    "create_challenge",
    "delete_recovery_codes",
    "generate_recovery_codes",
    "redeem_recovery_code",
    "resend_code",
    "verify_code",
]

OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
OTP_CODE_LENGTH = 6


def _otp_setting(name: str, default: int) -> int:
    """Read a 2FA knob from Django settings at call time so tests can
    override it with ``@override_settings`` (module-level constants would be
    frozen at import)."""
    return int(getattr(settings, name, default))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    # secrets.randbelow avoids the modulo bias of random.randint.
    return f"{secrets.randbelow(10**OTP_CODE_LENGTH):0{OTP_CODE_LENGTH}d}"


def _mask_email(email: str) -> str:
    """``rahim.hossain@rentora.com`` → ``r*****@rentora.com``."""
    local, _, domain = email.partition("@")
    if not domain:
        return email
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


def _deliver_code(user, code: str) -> None:
    """Send the one-time code to the user's email address."""
    send_mail(
        subject="Your Rentora verification code",
        message=(
            f"Hi {user.first_name or user.username},\n\n"
            f"Your Rentora sign-in verification code is: {code}\n\n"
            "This code expires in 10 minutes. If you did not try to sign in, "
            "you can safely ignore this email — your account is protected.\n\n"
            "— The Rentora Team"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def create_challenge(user, purpose: str = OTPChallenge.Purpose.LOGIN) -> OTPChallenge:
    """Close stale challenges and mint a fresh one for ``user``.

    ``purpose`` distinguishes login challenges from the email-ownership
    check used when *enabling* 2FA. Returns the challenge; the caller is
    responsible for reading the plain code from ``challenge.code`` — it is
    exposed only at creation time (the DB row stores the hash).
    """
    # A previously-issued challenge must not remain usable once the user
    # signs in again — otherwise an old leaked challenge could replay.
    OTPChallenge.objects.filter(
        user=user, purpose=purpose, status=OTPChallenge.Status.PENDING
    ).update(status=OTPChallenge.Status.EXPIRED)

    challenge_token = secrets.token_urlsafe(32)
    code = _generate_code()
    now = timezone.now()
    challenge = OTPChallenge.objects.create(
        user=user,
        purpose=purpose,
        challenge_token_hash=_sha256(challenge_token),
        code_hash=_sha256(code),
        expires_at=now
        + timezone.timedelta(seconds=_otp_setting("OTP_TTL_SECONDS", OTP_TTL_SECONDS)),
    )
    _deliver_code(user, code)
    # Expose the plain code and token only to this caller, never through the
    # ORM-to-API path.
    challenge.code = code
    challenge.challenge_token = challenge_token
    return challenge


def verify_code(challenge: OTPChallenge, code: str) -> tuple[bool, str]:
    """Validate ``code`` against ``challenge``.

    Returns ``(ok, message)``. Consumes the challenge on success, increments
    and locks on repeated failure. ``code`` must be a plain 6-digit string.
    """
    now = timezone.now()

    if challenge.status == OTPChallenge.Status.USED:
        return False, "This code has already been used. Please sign in again."
    if challenge.status == OTPChallenge.Status.LOCKED:
        return False, "Too many incorrect attempts. Please request a new code."
    if challenge.status == OTPChallenge.Status.EXPIRED:
        return False, "This code has expired. Please sign in again."
    if now >= challenge.expires_at:
        challenge.status = OTPChallenge.Status.EXPIRED
        challenge.save(update_fields=["status"])
        return False, "This code has expired. Please request a new one."

    if secrets.compare_digest(_sha256(code.strip()), challenge.code_hash):
        challenge.status = OTPChallenge.Status.USED
        challenge.save(update_fields=["status"])
        return True, ""

    challenge.attempts += 1
    max_attempts = _otp_setting("OTP_MAX_ATTEMPTS", OTP_MAX_ATTEMPTS)
    if challenge.attempts >= max_attempts:
        challenge.status = OTPChallenge.Status.LOCKED
        challenge.save(update_fields=["attempts", "status"])
        return False, "Too many incorrect attempts. Please request a new code."
    challenge.save(update_fields=["attempts"])
    remaining = max_attempts - challenge.attempts
    return False, f"Incorrect code. {remaining} attempt(s) remaining."


# ============================================================
# Recovery codes (2FA backup)
# ============================================================

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_GROUPS = 3
RECOVERY_CODE_GROUP_LEN = 4


def _format_recovery(code: str) -> str:
    """``AbCdEfGh1234`` → ``AbCd-EfGh-1234`` (uppercased)."""
    code = code.upper()
    return "-".join(
        code[i : i + RECOVERY_CODE_GROUP_LEN] for i in range(0, len(code), RECOVERY_CODE_GROUP_LEN)
    )


def generate_recovery_codes(user) -> list[str]:
    """Mint a fresh batch of one-time backup codes for ``user``.

    Returns the plaintext codes (shown to the user exactly once). Only their
    SHA-256 hashes are persisted; any previous batch is replaced.
    """
    from .models import RecoveryCode

    RecoveryCode.objects.filter(user=user).delete()
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_urlsafe(RECOVERY_CODE_GROUP_LEN)[:12]
        plain = _format_recovery(raw)
        RecoveryCode.objects.create(user=user, code_hash=_sha256(plain))
        codes.append(plain)
    return codes


def redeem_recovery_code(user, code: str) -> bool:
    """Mark ``code`` used if it belongs to ``user`` and is still unused."""
    from .models import RecoveryCode

    normalized = code.strip().upper()
    matches = RecoveryCode.objects.filter(user=user, code_hash=_sha256(normalized))
    if not matches.exists():
        return False
    # Single-use: claim atomically via used_at (a second concurrent request
    # will find it used).
    claimed = matches.filter(used_at__isnull=True).update(used_at=timezone.now())
    return claimed == 1


def delete_recovery_codes(user) -> int:
    """Remove every recovery code for ``user`` (called on 2FA disable)."""
    from .models import RecoveryCode

    deleted, _ = RecoveryCode.objects.filter(user=user).delete()
    return deleted


def resend_code(challenge: OTPChallenge) -> tuple[bool, str]:
    """Re-send the code for ``challenge`` (cooldown-guarded)."""
    now = timezone.now()
    if challenge.status == OTPChallenge.Status.USED:
        return False, "This challenge has already been completed."
    if now >= challenge.expires_at:
        challenge.status = OTPChallenge.Status.EXPIRED
        challenge.save(update_fields=["status"])
        return False, "This code has expired. Please sign in again."

    if (
        challenge.created_at
        + timezone.timedelta(
            seconds=_otp_setting("OTP_RESEND_COOLDOWN_SECONDS", OTP_RESEND_COOLDOWN_SECONDS)
        )
        > now
    ):
        return False, "Please wait a moment before requesting another code."

    code = _generate_code()
    challenge.code_hash = _sha256(code)
    challenge.attempts = 0
    challenge.expires_at = now + timezone.timedelta(
        seconds=_otp_setting("OTP_TTL_SECONDS", OTP_TTL_SECONDS)
    )
    challenge.save(update_fields=["code_hash", "attempts", "expires_at"])
    _deliver_code(challenge.user, code)
    challenge.code = code
    return True, ""
