import uuid

from django.conf import settings
from django.db import models

from bookings.models import Booking


class Payment(models.Model):
    class Method(models.TextChoices):
        SSLCOMMERZ = "sslcommerz", "SSLCommerz"
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        MANUAL = "manual", "Manual"

    class Type(models.TextChoices):
        BOOKING_DEPOSIT = "booking_deposit", "Booking Deposit"
        MONTHLY_RENT = "monthly_rent", "Monthly Rent"
        SECURITY_DEPOSIT = "security_deposit", "Security Deposit"
        # Paid-listing promotions (monetization). These have no `booking` —
        # they're attached to a `room` instead, and on success upgrade the
        # room's tier for LISTING_TIER_DURATION_DAYS.
        LISTING_FEATURE = "listing_feature", "Listing Feature"
        LISTING_PREMIUM = "listing_premium", "Listing Premium"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    # Nullable since booking-less payments exist: listing tier promotions.
    # Every payment still has exactly one subject — a booking (rent/deposit)
    # or a room (featured/premium promotion) — and callbacks use whichever is
    # set to apply the success side effects.
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="payments", null=True, blank=True
    )
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.CASCADE,
        related_name="promotion_payments",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=Method.choices, default=Method.SSLCOMMERZ
    )
    payment_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED)

    # Our own reference, generated server-side — sent to the gateway as `tran_id`.
    transaction_id = models.CharField(max_length=64, unique=True, blank=True)
    # The gateway's own reference for this transaction (SSLCommerz val_id, bKash trxID, ...).
    gateway_transaction_id = models.CharField(max_length=128, blank=True)
    # Full raw gateway response, kept for audit/debugging.
    gateway_response = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_id} ({self.status}) - {self.amount} BDT"

    def transition_status(
        self, new_status, *, changed_by="system", metadata=None, extra_update_fields=None
    ):
        """Move this payment to ``new_status`` and record a
        :class:`PaymentAuditLog` entry for it in the same call.

        This is the single place that mutates `Payment.status` so every
        transition — gateway callback, refund, initiate failure — is
        guaranteed to leave an audit trail, rather than relying on every call
        site to remember to log it separately.
        """
        old_status = self.status
        self.status = new_status
        update_fields = {"status", "updated_at"} | set(extra_update_fields or [])
        self.save(update_fields=list(update_fields))

        if old_status != new_status:
            PaymentAuditLog.objects.create(
                payment=self,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                metadata=metadata or {},
            )


class PaymentAuditLog(models.Model):
    """Immutable record of every status transition a Payment goes through."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="audit_logs")
    old_status = models.CharField(max_length=10, blank=True)
    new_status = models.CharField(max_length=10)
    # "system" for gateway-callback-driven transitions, "user:<id>" for
    # transitions a human explicitly triggered (e.g. a landlord's refund).
    changed_by = models.CharField(max_length=32, default="system")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["payment", "created_at"])]

    def __str__(self):
        return f"{self.payment_id}: {self.old_status} -> {self.new_status}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="invoices")
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="invoice")
    # Sequential, human-facing reference, e.g. "INV-2026-0001". Generated
    # server-side (see payments/services/invoice.py) — never client-supplied.
    invoice_number = models.CharField(max_length=32, unique=True, editable=False)
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_number


class PaymentSchedule(models.Model):
    """One installment (e.g. one month's rent) in a booking's payment plan.

    Generated when a booking is approved (see payments/services/schedule.py)
    so tenants and landlords can see the full advance schedule up front, not
    just payments already made.
    """

    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        DUE = "due", "Due"
        OVERDUE = "overdue", "Overdue"
        PAID = "paid", "Paid"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payment_schedules")
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPCOMING)
    # Set once the corresponding real Payment succeeds; nullable until then.
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="schedule_entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]
        indexes = [models.Index(fields=["booking", "due_date"])]

    def __str__(self):
        return f"{self.booking_id}: {self.amount} due {self.due_date} ({self.status})"
