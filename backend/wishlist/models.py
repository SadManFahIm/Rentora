from django.conf import settings
from django.db import models

from rooms.models import Room


class Wishlist(models.Model):
    """A single saved-room entry linking a user to a room they bookmarked.

    The ``unique_together`` constraint guarantees a user cannot wishlist the
    same room twice, which lets the toggle endpoint treat existence as a
    boolean switch.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "room")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} ♥ {self.room}"
