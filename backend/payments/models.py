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

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Method.choices, default=Method.SSLCOMMERZ)
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
