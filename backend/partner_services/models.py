"""Insurance & credit partner abstractions.

External partners plug in behind a provider interface (mirroring
``users.kyc_provider``): a deterministic rule-based implementation is the
default, with an optional HTTP gateway selected by settings.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Partner(models.Model):
    """An external partner (insurer or credit provider)."""

    class Kind(models.TextChoices):
        INSURANCE = "insurance", "Insurance"
        CREDIT = "credit", "Credit"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    api_endpoint = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"


class InsuranceProduct(models.Model):
    """An insurable product offered by an insurance partner."""

    partner = models.ForeignKey(
        Partner, on_delete=models.CASCADE, related_name="insurance_products"
    )
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    coverage = models.JSONField(default=dict, blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price_monthly"]

    def __str__(self):
        return f"{self.name} ({self.partner.name})"


class InsuranceQuote(models.Model):
    """A user's insurance quote for a product (optionally tied to a room)."""

    class Status(models.TextChoices):
        QUOTED = "quoted", "Quoted"
        ISSUED = "issued", "Issued"
        DECLINED = "declined", "Declined"
        CANCELED = "canceled", "Canceled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="insurance_quotes"
    )
    product = models.ForeignKey(InsuranceProduct, on_delete=models.PROTECT, related_name="quotes")
    room = models.ForeignKey(
        "rooms.Room", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    broker = models.ForeignKey(
        "brokers.BrokerProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    coverage_period = models.PositiveIntegerField(default=12)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUOTED)
    quote_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quote for {self.user_id} on {self.product_id} ({self.status})"
