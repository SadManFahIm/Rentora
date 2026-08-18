"""Phone (SMS) OTP login service — passwordless sign-in with a 6-digit code.

Security mirrors the email-OTP service (``users/services.py``):

- The code is stored as a SHA-256 hash only — a DB leak never yields
  replayable codes, and no endpoint ever returns the plaintext.
- One active challenge per phone number; requesting a new code (or a resend)
  first expires the old one.
- Challenges expire after a short TTL, lock after a bounded number of failed
  attempts, and a cooldown guards re-requests.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.utils import timezone

from .models import SmsOtpChallenge

SMS_OTP_CODE_LENGTH = 6


class CooldownError(Exception):
    """Raised when a new code is requested too soon after the previous one."""

    def __init__(self, remaining: int) -> None:
        super().__init__(remaining)
        self.remaining = remaining


def _setting(name: str, default: int) -> int:
    """Read a knob at call time so tests can override with @override_settings."""
    return int(getattr(settings, name, default))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    # secrets.randbelow avoids the modulo bias of random.randint.
    return f"{secrets.randbelow(10**SMS_OTP_CODE_LENGTH):0{SMS_OTP_CODE_LENGTH}d}"


def create_sms_challenge(phone: str) -> tuple[SmsOtpChallenge, str, int]:
    """Mint a fresh challenge for ``phone`` and deliver the code.

    Raises ``CooldownError`` if the previous challenge is still in its
    cooldown window. Returns ``(challenge, masked_phone, ttl_seconds)`` — the
    plaintext code is never returned; only delivered by SMS.
    """
    ttl = _setting("SMS_OTP_TTL_SECONDS", 600)
    cooldown = _setting("SMS_OTP_RESEND_COOLDOWN_SECONDS", 30)
    now = timezone.now()

    last = SmsOtpChallenge.objects.filter(phone=phone).order_by("-created_at").first()
    if last is not None and last.status == SmsOtpChallenge.Status.PENDING:
        elapsed = (now - last.created_at).total_seconds()
        if elapsed < cooldown:
            raise CooldownError(remaining=int(cooldown - elapsed))
        last.status = SmsOtpChallenge.Status.EXPIRED
        last.save(update_fields=["status"])

    code = _generate_code()
    challenge = SmsOtpChallenge.objects.create(
        phone=phone,
        code_hash=_sha256(code),
        expires_at=now + timezone.timedelta(seconds=ttl),
    )
    # Delivery is best-effort and never raises (see users/sms.send_sms).
    from .sms import mask_phone, send_sms

    send_sms(phone, code)
    return challenge, mask_phone(phone), ttl


def verify_sms_code(phone: str, code: str) -> tuple[bool, str]:
    """Validate ``code`` against the phone's most recent challenge.

    Returns ``(ok, message)``. Consumes the challenge on success; increments
    and locks on repeated failure. Mirrors ``users.services.verify_code``.
    """
    now = timezone.now()
    challenge = SmsOtpChallenge.objects.filter(phone=phone).order_by("-created_at").first()
    if challenge is None:
        return (
            False,
            "No verification was requested for this number yet. Please request a code first.",
        )
    if challenge.status == SmsOtpChallenge.Status.USED:
        return False, "This code has already been used. Please sign in again."
    if challenge.status == SmsOtpChallenge.Status.LOCKED:
        return False, "Too many incorrect attempts. Please request a new code."
    if challenge.status == SmsOtpChallenge.Status.EXPIRED or now >= challenge.expires_at:
        if challenge.status != SmsOtpChallenge.Status.EXPIRED:
            challenge.status = SmsOtpChallenge.Status.EXPIRED
            challenge.save(update_fields=["status"])
        return False, "This code has expired. Please request a new one."

    if secrets.compare_digest(_sha256(code.strip()), challenge.code_hash):
        challenge.status = SmsOtpChallenge.Status.USED
        challenge.save(update_fields=["status"])
        return True, ""

    challenge.attempts += 1
    max_attempts = _setting("SMS_OTP_MAX_ATTEMPTS", 5)
    if challenge.attempts >= max_attempts:
        challenge.status = SmsOtpChallenge.Status.LOCKED
        challenge.save(update_fields=["attempts", "status"])
        return False, "Too many incorrect attempts. Please request a new code."
    challenge.save(update_fields=["attempts"])
    return False, f"Incorrect code. {max_attempts - challenge.attempts} attempt(s) remaining."
