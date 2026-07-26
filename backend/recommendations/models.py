from django.conf import settings
from django.db import models

from rooms.models import Room


class UserActivity(models.Model):
    """A single signal of interest a user expressed toward a room.

    This is the raw event log the recommendation services (content-based,
    collaborative) are built on top of — each row is one interaction, weighted
    by how strong a signal of interest that interaction type represents.
    """

    class ActivityType(models.TextChoices):
        VIEW = "view", "View"
        SEARCH = "search", "Search"
        WISHLIST = "wishlist", "Wishlist"
        BOOKING_REQUEST = "booking_request", "Booking Request"
        BOOKING_APPROVED = "booking_approved", "Booking Approved"

    # Default weight per activity type — stronger signals of genuine interest
    # (an approved booking) count far more than a passive one (a page view).
    DEFAULT_WEIGHTS = {
        ActivityType.VIEW: 1,
        ActivityType.SEARCH: 1,
        ActivityType.WISHLIST: 3,
        ActivityType.BOOKING_REQUEST: 5,
        ActivityType.BOOKING_APPROVED: 10,
    }

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activities")
    # Nullable: a `search` activity isn't about one room, it's a query across
    # many — `metadata` carries the query text instead.
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="activities", null=True, blank=True)
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    weight = models.IntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "activity_type"]),
            models.Index(fields=["room"]),
        ]
        verbose_name_plural = "user activities"

    def save(self, *args, **kwargs):
        if not self.weight:
            self.weight = self.DEFAULT_WEIGHTS.get(self.activity_type, 1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} {self.activity_type} {self.room or ''}".strip()
