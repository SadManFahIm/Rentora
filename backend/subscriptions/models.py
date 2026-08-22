"""Recurring plans + entitlements — the reusable SaaS core of Phase 15.

A ``Plan`` is a priced bundle of ``features`` (string keys). A user's
active ``Subscription`` grants the features of its plan; every paid feature
in the platform is checked server-side through
:func:`subscriptions.services.entitlements.check_entitlement` — never from
the client.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q


class Plan(models.Model):
    """A purchasable subscription plan (bundle of feature keys)."""

    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_cycle = models.CharField(
        max_length=10, choices=BillingCycle.choices, default=BillingCycle.MONTHLY
    )
    # List of feature keys (e.g. "price_prediction_v2", "analytics_export").
    features = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.code} ({self.price} BDT/{self.billing_cycle})"

    def has_feature(self, feature: str) -> bool:
        return feature in (self.features or [])


class Subscription(models.Model):
    """A user's subscription to a plan.

    Lifecycle: ``pending`` (checkout started) → ``active`` (gateway payment
    succeeded) → ``canceled`` (will stop at period end) / ``expired`` (period
    ended without renewal) / ``past_due``. Only one non-terminal subscription
    may exist per user (unique partial constraint).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"
        PAST_DUE = "past_due", "Past Due"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    cancel_at_period_end = models.BooleanField(default=False)
    # The gateway payment that activated (or is activating) this subscription.
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status__in=["pending", "active", "past_due"]),
                name="unique_active_subscription_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id} → {self.plan_id} ({self.status})"

    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    def period_days(self) -> int:
        return (
            settings.SUBSCRIPTION_PERIOD_DAYS.get(self.plan.billing_cycle)
            or settings.SUBSCRIPTION_PERIOD_DAYS["monthly"]
        )
