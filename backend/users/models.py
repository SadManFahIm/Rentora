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


class OTPChallenge(models.Model):
    """A single in-flight email-OTP authentication challenge.

    Created when a user with ``otp_enabled`` signs in with the correct
    password. The challenge token (returned to the client) and the 6-digit
    code (mailed to the user) are stored only as SHA-256 hashes so a database
    leak never exposes codes that can be replayed.

    Lifecycle: pending → used (correct code) | expired (TTL passed) |
    locked (too many failed attempts).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        USED = "used", "Used"
        EXPIRED = "expired", "Expired"
        LOCKED = "locked", "Locked"

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="otp_challenges")
    challenge_token_hash = models.CharField(max_length=64, db_index=True)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user_id} ({self.status})"
