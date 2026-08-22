import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from config.storage import private_media_storage


class User(AbstractUser):
    class Role(models.TextChoices):
        TENANT = "tenant", "Tenant"
        LANDLORD = "landlord", "Landlord"
        ADMIN = "admin", "Admin"
        # Phase 15 — Monetization 2.0: verified middlemen who refer tenants
        # and earn commissions on approved bookings.
        BROKER = "broker", "Broker"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    # Enforce uniqueness at the database layer too — registration validates
    # it, but admins/shells/imports must not be able to create duplicates.
    email = models.EmailField("email address", blank=True, unique=True)

    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TENANT)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    nid_verified = models.BooleanField(default=False)
    # Two-sided trust (Phase 12): identity verification for *tenants*. The
    # full lifecycle lives on ``TenantVerification``; this cached boolean is
    # what public serializers (chat, profiles, bookings) expose so landlords
    # see only "Verified Tenant" — never the document itself.
    tenant_verified = models.BooleanField(default=False)
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Two-factor authentication (email OTP). Off by default so the demo
    # accounts and new signups are unaffected; enabled per-account from the
    # dashboard after the user confirms their current password.
    otp_enabled = models.BooleanField(default=False)

    # Referral program (Phase 10): a short code on every account that friends
    # can use at signup (`/auth/register?ref=CODE`), plus a back-reference to
    # who brought this user in.
    referral_code = models.CharField(
        max_length=12, unique=True, null=True, blank=True, editable=False
    )
    referred_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )
    # Public token for sharing a wishlist — random, unguessable, revocable.
    wishlist_share_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Daily saved-search digest email (Tier-1 quick win): the user opts in to
    # receive one summary email per day when their saved searches matched new
    # listings. Default on; off silences the digest without touching in-app
    # or push alerts.
    digest_emails_enabled = models.BooleanField(default=True)

    # Weekly rental market report email (Phase 15, C6): opt-in newsletter with
    # the per-area price/demand snapshot. Default off — nobody gets market
    # emails unless they ask.
    market_report_emails_enabled = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            import secrets
            import string

            alphabet = string.ascii_uppercase + string.digits
            for _ in range(5):
                code = "".join(secrets.choice(alphabet) for _ in range(8))
                if not User.objects.filter(referral_code=code).exists():
                    self.referral_code = code
                    break
            else:  # pragma: no cover - 5 attempts at 8 chars is astronomically safe
                self.referral_code = "".join(secrets.choice(alphabet) for _ in range(12))
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class KycDocument(models.Model):
    """A KYC proof (NID or passport scan) submitted by a user for verification.

    Privacy contract: document *files* are only ever exposed to the owner
    (via the authenticated "my documents" endpoint) and to staff/admins (via
    the review-panel endpoints). They never appear in public room/user
    serializers, and no public endpoint references this model.

    Lifecycle: pending -> approved | rejected (admin decision, recorded on
    ``review_note``). Approving a document is what gates ``User.nid_verified``
    in the admin panel flow; the two stay consistent because the review view
    flips ``nid_verified`` in the same transaction.
    """

    class DocType(models.TextChoices):
        NID = "nid", "National ID (NID)"
        PASSPORT = "passport", "Passport"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="kyc_documents")
    doc_type = models.CharField(max_length=10, choices=DocType.choices)
    # FileField (not ImageField) so PDF scans are accepted too — admins
    # preview the file in-browser (images render inline, PDFs via viewer).
    # Stored in PRIVATE media (config/storage.PrivateMediaStorage), outside the
    # public MEDIA_ROOT, and only ever served through the authenticated
    # document endpoint.
    file = models.FileField(upload_to="kyc_documents/%Y/%m/", storage=private_media_storage)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} for {self.user_id} ({self.status})"


class TenantVerification(models.Model):
    """A tenant's identity verification — the tenant side of two-sided trust.

    Privacy contract (mirrors ``KycDocument``): the identity document is only
    ever exposed to the tenant themselves and to staff/admins via the
    auth-gated review endpoints. Landlords never see the document or any raw
    NID data — public serializers expose only ``User.tenant_verified`` (the
    cached boolean this record drives), so a landlord sees at most
    "Verified Tenant" / "Verification Pending" / "Not Verified".

    Lifecycle: not_started → pending (document submitted) → verified | rejected
    | needs_review (admin decision, recorded on ``review_note``). A rejected
    or expired record can be re-submitted (back to pending); a verified record
    carries an ``expires_at`` so identity verification doesn't last forever.
    Every transition is written to the append-only audit log (``tenant_kyc.*``)
    and the tenant is notified, so the trail is complete.
    """

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        NEEDS_REVIEW = "needs_review", "Needs Review"

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="tenant_verification"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    doc_type = models.CharField(max_length=10, choices=KycDocument.DocType.choices, blank=True)
    # FileField (not ImageField) so PDF scans are accepted too. Files are
    # renamed to a UUID on upload so an original filename containing an NID
    # number never reaches storage, logs, or error reports. Stored in PRIVATE
    # media (never the public MEDIA_ROOT) and served only via the auth-gated
    # document endpoint.
    file = models.FileField(
        upload_to="tenant_kyc/%Y/%m/", blank=True, storage=private_media_storage
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Automated pre-screening (Tier 2, see users/kyc_auto.py): a deterministic
    # first pass over the document that *recommends* a decision for the admin
    # queue (it never decides alone). ``auto_screen_detail`` carries the
    # human-readable reasons so the recommendation is explainable/auditable.
    auto_screen_score = models.IntegerField(null=True, blank=True)
    auto_screen_result = models.CharField(max_length=24, null=True, blank=True)
    auto_screen_detail = models.JSONField(default=dict, blank=True)

    # Phase 17 — KYC Liveness + Face-Match (Stage 2 foundation)
    liveness_status = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Liveness check status: empty (not started), pending, passed, failed, needs_review.",
    )
    liveness_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Liveness confidence score 0-100 from the provider.",
    )
    face_match_status = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Face-match status: empty (not started), pending, passed, failed, needs_review.",
    )
    face_match_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Face-match similarity score 0-100 from the provider.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Tenant verification for {self.user_id} ({self.status})"


class OTPChallenge(models.Model):
    """A single in-flight email-OTP challenge.

    Created for two distinct purposes:

    - ``login`` — a 2FA-enabled user signed in with the correct password;
      the challenge token (returned to the client) and the 6-digit code
      (mailed to the user) are stored only as SHA-256 hashes.
    - ``enable_2fa`` — a user confirmed their password to *enable* 2FA; the
      emailed code proves email ownership before ``otp_enabled`` flips on.

    Lifecycle: pending → used | expired (TTL passed) | locked (too many
    failed attempts).
    """

    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"
        ENABLE_2FA = "enable_2fa", "Enable 2FA"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        USED = "used", "Used"
        EXPIRED = "expired", "Expired"
        LOCKED = "locked", "Locked"

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="otp_challenges")
    purpose = models.CharField(max_length=16, choices=Purpose.choices, default=Purpose.LOGIN)
    challenge_token_hash = models.CharField(max_length=64, db_index=True)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user_id} ({self.purpose}:{self.status})"


class SmsOtpChallenge(models.Model):
    """A single in-flight phone (SMS) login challenge (Phase 13).

    Passwordless sign-in: the user enters a Bangladeshi mobile number, a
    6-digit code is delivered by SMS, and a correct code signs them in —
    creating the account on the first successful verification. The code is
    stored as a SHA-256 hash only; one active challenge per phone number.

    Lifecycle: pending → used | expired (TTL passed) | locked (too many
    failed attempts). Mirrors ``OTPChallenge``.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        USED = "used", "Used"
        EXPIRED = "expired", "Expired"
        LOCKED = "locked", "Locked"

    phone = models.CharField(max_length=16, db_index=True)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SMS OTP for {self.phone} ({self.status})"


class RecoveryCode(models.Model):
    """One-time backup code minted when a user enables 2FA.

    The user is shown the plaintext codes exactly once (at generation); only
    SHA-256 hashes are stored. Each code is single-use and survives until
    2FA is disabled (which deletes them all).
    """

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Recovery code for {self.user_id} (used={self.used_at is not None})"


class PasskeyCredential(models.Model):
    """A WebAuthn/FIDO2 credential (passkey) registered to a user.

    Only the public key is stored — the private key never leaves the user's
    authenticator. ``sign_count`` is updated on every authentication and
    checked for replay/clone detection.
    """

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="passkeys")
    # Raw credential id bytes (base64url-encoded by the client).
    credential_id = models.CharField(max_length=512, unique=True)
    public_key = models.TextField()  # CBOR-encoded public key
    sign_count = models.PositiveIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    name = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Passkey {self.name or self.credential_id[:8]} for {self.user_id}"


# ============================================================
# Phase 17 — KYC Liveness + Face-Match (Stage 4)
# ============================================================


class LivenessChallenge(models.Model):
    """A single liveness-detection challenge for KYC verification.

    Lifecycle: pending → passed | failed | expired.
    Selfies are stored in private media and auto-deleted after 90 days.

    The challenge tracks which provider was used and what the provider
    returned, so the admin can audit any automated decision.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    class ChallengeType(models.TextChoices):
        BLINK = "blink", "Blink Detection"
        SMILE = "smile", "Smile Detection"
        TURN_HEAD = "turn_head", "Turn Head"
        TEXT_CHALLENGE = "text_challenge", "Follow Instructions"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="liveness_challenges",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    challenge_type = models.CharField(
        max_length=20,
        choices=ChallengeType.choices,
        default=ChallengeType.BLINK,
    )
    selfie = models.ImageField(
        upload_to="kyc/liveness/%Y/%m/",
        storage=private_media_storage,
        blank=True,
        null=True,
        help_text="User selfie captured during liveness check (private, auto-deleted after 90 days).",
    )
    provider_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Name of the liveness provider used (e.g. 'rules', 'http').",
    )
    provider_score = models.IntegerField(
        null=True,
        blank=True,
        help_text="Provider confidence score 0-100.",
    )
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw provider response for audit trail.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Challenge expires after this time (default 15 minutes).",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"Liveness challenge for user {self.user_id} ({self.status}, {self.challenge_type})"

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone as _tz

        if self.expires_at is None:
            return False
        return _tz.now() > self.expires_at


class LivenessConsent(models.Model):
    """Tracks user consent for liveness detection and face-match.

    Required before collecting any biometric data (selfies, face embeddings).
    Each consent grant/revoke is auditable via timestamps + IP.
    """

    class ConsentType(models.TextChoices):
        LIVENESS = "liveness", "Liveness Detection"
        FACE_MATCH = "face_match", "Face Match Comparison"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="liveness_consents",
    )
    consent_type = models.CharField(
        max_length=20,
        choices=ConsentType.choices,
    )
    granted = models.BooleanField(
        default=False,
        help_text="True if user has granted consent.",
    )
    granted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-granted_at"]
        unique_together = [("user", "consent_type")]

    def __str__(self):
        state = "granted" if self.granted else "revoked"
        return f"Consent({self.consent_type}) for user {self.user_id}: {state}"
