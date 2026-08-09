from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        TENANT = "tenant", "Tenant"
        LANDLORD = "landlord", "Landlord"
        ADMIN = "admin", "Admin"

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
    bio = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Two-factor authentication (email OTP). Off by default so the demo
    # accounts and new signups are unaffected; enabled per-account from the
    # dashboard after the user confirms their current password.
    otp_enabled = models.BooleanField(default=False)

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
    file = models.FileField(upload_to="kyc_documents/%Y/%m/")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} for {self.user_id} ({self.status})"


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
