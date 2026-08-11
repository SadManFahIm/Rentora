from django.conf import settings
from django.db import models


class Notification(models.Model):
    """An in-app notification addressed to a single user.

    Notifications are created by :func:`notifications.utils.create_notification`
    (directly or via booking/review signals) and consumed by the notification
    API. ``action_url`` is an optional client-side route the frontend can link
    the notification to (e.g. ``/dashboard/bookings``).
    """

    class Type(models.TextChoices):
        BOOKING_REQUEST = "booking_request", "Booking Request"
        BOOKING_APPROVED = "booking_approved", "Booking Approved"
        BOOKING_REJECTED = "booking_rejected", "Booking Rejected"
        BOOKING_CANCELLED = "booking_cancelled", "Booking Cancelled"
        NEW_REVIEW = "new_review", "New Review"
        NEW_MESSAGE = "new_message", "New Message"
        PAYMENT_SUCCESS = "payment_success", "Payment Success"
        PAYMENT_FAILED = "payment_failed", "Payment Failed"
        PAYMENT_REMINDER = "payment_reminder", "Payment Reminder"
        ROOMMATE_REQUEST = "roommate_request", "Roommate Request"
        ROOMMATE_APPROVED = "roommate_approved", "Roommate Approved"
        FRAUD_FLAG = "fraud_flag", "Fraud Flag"
        KYC_SLA_BREACH = "kyc_sla_breach", "KYC SLA Breach"
        SAVED_SEARCH_MATCH = "saved_search_match", "Saved Search Match"
        SYSTEM = "system", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    action_url = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_notification_type_display()}] {self.title} → {self.user}"


class EmailDeliveryLog(models.Model):
    """Delivery ledger for rate-limited alert emails.

    Every attempt to send an alert email (e.g. the KYC SLA breach blast)
    records one row here so the team can see what went out, what was
    throttled, and what failed — and so the sender can enforce per-recipient
    daily budgets and failure backoff without an external rate limiter.
    """

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped (rate limit / backoff)"

    recipient = models.EmailField()
    template_name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    attempt = models.PositiveIntegerField(default=1)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "template_name", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_status_display()}] {self.template_name} → {self.recipient}"


class PushSubscription(models.Model):
    """A browser's Web Push subscription for one user.

    Stored so the backend can deliver push notifications (booking updates,
    chat messages, fraud flags, KYC decisions, price drops) even when the
    user isn't looking at the app. Endpoints are device-specific — one user
    can hold several (phone, laptop, …). A subscription is removed the first
    time the push service reports it dead (410 Gone).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    auth = models.CharField(max_length=200)
    p256dh = models.CharField(max_length=300)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"push {self.user} · {self.endpoint[:60]}…"
