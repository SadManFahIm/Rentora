from django.conf import settings
from django.db import models


class SavedSearch(models.Model):
    """A room-search query a user saved to be alerted about new matches.

    The filters mirror the Rooms list endpoint's query params so the same
    matching logic powers both: ``q`` (full-text), ``area``, ``room_type``,
    ``gender_preference``, ``price_min``/``price_max``, ``verified``. The
    daily ``check_saved_searches`` beat task finds rooms *created since the
    last check* and notifies the user via an in-app notification.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches"
    )
    name = models.CharField(max_length=120)
    filters = models.JSONField(default=dict, blank=True)
    # Set to now() each time a check runs (whether or not matches were found),
    # so rooms are never alerted about twice.
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"{self.user}: {self.name}"
