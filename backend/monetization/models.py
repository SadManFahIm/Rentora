"""Central revenue domain: commission rules, commissions, the revenue
ledger, and payouts — shared by brokers, corporate, marketplace and
insurance/credit partners.

Money discipline: every amount is a ``Decimal`` computed server-side; every
mutation that can be replayed is guarded by a unique ``idempotency_key``; and
every mutation is written to the append-only audit log.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CommissionRule(models.Model):
    """The platform's commission rate for a revenue scope.

    Rates are percentages (e.g. ``2.0`` = 2%). An active rule overrides the
    ``COMMISSION_DEFAULT_RATES`` settings fallback for its scope.
    """

    class Scope(models.TextChoices):
        BROKER = "broker", "Broker"
        CORPORATE = "corporate", "Corporate"
        MARKETPLACE = "marketplace", "Marketplace"
        INSURANCE = "insurance", "Insurance"
        CREDIT = "credit", "Credit"

    scope = models.CharField(max_length=20, choices=Scope.choices, unique=True)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope"]

    def __str__(self):
        return f"{self.scope}: {self.rate}%"


class Commission(models.Model):
    """A single commission earned by a partner (broker/provider/insurance).

    ``source_type``/``source_id`` point at the originating transaction
    (Booking, AddonOrder, InsuranceQuote). Idempotency is guaranteed by the
    unique ``idempotency_key`` — re-processing an approval/confirmation never
    double-pays.
    """

    class Kind(models.TextChoices):
        BROKER_BOOKING = "broker_booking", "Broker Booking"
        CORPORATE_BOOKING = "corporate_booking", "Corporate Booking"
        MARKETPLACE_ORDER = "marketplace_order", "Marketplace Order"
        INSURANCE_POLICY = "insurance_policy", "Insurance Policy"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"

    kind = models.CharField(max_length=24, choices=Kind.choices)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commissions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    detail = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    def __str__(self):
        return f"{self.kind} for {self.recipient_id}: {self.amount} BDT ({self.status})"


class RevenueLedgerEntry(models.Model):
    """One auditable money movement through the platform.

    ``platform_amount`` is the platform's recognized revenue from the
    transaction; ``partner_amount`` is the obligation to a partner
    (broker/provider/insurer). Idempotent by ``idempotency_key``.
    """

    class EntryType(models.TextChoices):
        SUBSCRIPTION_PAYMENT = "subscription_payment", "Subscription Payment"
        SUBSCRIPTION_RENEWAL = "subscription_renewal", "Subscription Renewal"
        LISTING_PROMOTION = "listing_promotion", "Listing Promotion"
        ADDON_SALE = "addon_sale", "Addon Sale"
        INSURANCE_POLICY = "insurance_policy", "Insurance Policy"
        CORPORATE_INVOICE = "corporate_invoice", "Corporate Invoice"
        COMMISSION_BROKER = "commission_broker", "Broker Commission"
        COMMISSION_CORPORATE = "commission_corporate", "Corporate Commission"
        PAYOUT = "payout", "Payout"
        REFUND = "refund", "Refund"

    class Scope(models.TextChoices):
        SUBSCRIPTION = "subscription", "Subscription"
        LISTING = "listing", "Listing"
        BROKER = "broker", "Broker"
        CORPORATE = "corporate", "Corporate"
        MARKETPLACE = "marketplace", "Marketplace"
        INSURANCE = "insurance", "Insurance"
        CREDIT = "credit", "Credit"

    entry_type = models.CharField(max_length=32, choices=EntryType.choices)
    scope = models.CharField(max_length=20, choices=Scope.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    partner_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="BDT")
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scope", "created_at"])]

    def __str__(self):
        return f"{self.entry_type} {self.gross_amount} BDT ({self.scope})"


class Payout(models.Model):
    """A payment the platform owes a partner (broker/provider/insurer)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected"
        CANCELED = "canceled", "Canceled"

    class Method(models.TextChoices):
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        BANK = "bank", "Bank Transfer"
        MANUAL = "manual", "Manual"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payouts"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=Method.choices)
    # Account details are masked at write time — never stored in plaintext.
    account_details = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True)
    reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_payouts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "status"])]

    def __str__(self):
        return f"Payout {self.amount} BDT → {self.recipient_id} ({self.status})"
