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
