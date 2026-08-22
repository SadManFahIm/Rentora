"""Broker network: verified middlemen who refer tenants to rooms and earn
commissions on approved bookings.

Verification mirrors the tenant-KYC pipeline (deterministic pre-screen +
admin decision) — see ``brokers.services.screen_broker``.
"""

from __future__ import annotations

import secrets
import string

from django.conf import settings
from django.db import models


class BrokerProfile(models.Model):
    """A broker's identity + verification state on the platform."""

    class Status(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="broker_profile"
    )
    license_number = models.CharField(max_length=64, blank=True)
    years_experience = models.PositiveIntegerField(default=0)
    specialization = models.CharField(max_length=120, blank=True)
    areas = models.JSONField(default=list, blank=True)
    # Short, shareable attribution code (e.g. /rooms?ref=AB12CD34).
    referral_code = models.CharField(max_length=12, unique=True, blank=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNVERIFIED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} broker ({self.status})"

    def is_verified(self) -> bool:
        return self.status == self.Status.VERIFIED

    def save(self, *args, **kwargs):
        if not self.referral_code:
            alphabet = string.ascii_uppercase + string.digits
            for _ in range(5):
                code = "".join(secrets.choice(alphabet) for _ in range(8))
                if not BrokerProfile.objects.filter(referral_code=code).exists():
                    self.referral_code = code
                    break
            else:  # pragma: no cover - collision odds are astronomically low
                self.referral_code = "".join(secrets.choice(alphabet) for _ in range(12))
        super().save(*args, **kwargs)


class BrokerVerification(models.Model):
    """One broker verification submission + its pre-screen + admin decision."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    profile = models.ForeignKey(
        BrokerProfile, on_delete=models.CASCADE, related_name="verifications"
    )
    # List of uploaded document URLs (license copy, trade license, ...).
    documents = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    auto_screen_score = models.IntegerField(null=True, blank=True)
    auto_screen_result = models.CharField(max_length=24, null=True, blank=True)
    auto_screen_detail = models.JSONField(default=dict, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="broker_reviews",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Broker verification {self.profile_id} ({self.status})"
