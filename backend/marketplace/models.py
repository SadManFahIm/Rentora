"""Add-on marketplace: third-party providers sell services (cleaning,
relocation, repairs, furniture, utilities, insurance) to tenants.

The platform takes a slice of every confirmed order (provider commission
share) and optionally pays a referring broker. Commissions and the revenue
ledger are written idempotently on CONFIRMED.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AddonProvider(models.Model):
    """A third-party service provider account."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addon_provider"
    )
    business_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # Provider's share (%) of each order's total — overrides the marketplace
    # CommissionRule when set.
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.business_name} ({self.status})"

    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class AddonService(models.Model):
    """A single purchasable add-on service."""

    class Category(models.TextChoices):
        CLEANING = "cleaning", "Cleaning"
        RELOCATION = "relocation", "Relocation"
        REPAIRS = "repairs", "Repairs"
        FURNITURE = "furniture", "Furniture"
        UTILITIES = "utilities", "Utilities"
        INSURANCE = "insurance", "Insurance"

    provider = models.ForeignKey(AddonProvider, on_delete=models.CASCADE, related_name="services")
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=40, default="job")
    is_active = models.BooleanField(default=True)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class AddonOrder(models.Model):
    """A tenant's order of an add-on service."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELED = "canceled", "Canceled"
        REFUNDED = "refunded", "Refunded"

    service = models.ForeignKey(AddonService, on_delete=models.PROTECT, related_name="orders")
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addon_orders"
    )
    # Optional referring broker (attribution → their commission).
    broker = models.ForeignKey(
        "brokers.BrokerProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    quantity = models.PositiveIntegerField(default=1)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.service_id} x{self.quantity} for {self.tenant_id} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.total:
            self.total = self.service.price * self.quantity
        super().save(*args, **kwargs)
