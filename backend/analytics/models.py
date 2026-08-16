"""Self-hosted analytics (Tier 2).

A lightweight, privacy-lean event store — no external analytics vendor, no
tracking pixels, nothing leaves the server. Product usage data stays
first-party and is queried directly for conversion funnels and the admin
Trust & Safety / growth dashboard.

Privacy contract:
- Events are metadata: an event name, a category, a path, a session id and
  a small free-form ``properties`` dict. We never ask clients to send PII
  (no email, name, phone, NID), and the capture endpoint rejects oversized
  payloads so the store can't become a data dump.
- ``user`` is linked only when the request is authenticated — anonymous
  visitors are tracked by ``session_id`` alone.
"""

from django.conf import settings
from django.db import models

# Bounds on a single event payload — generous for legit product events,
# small enough that the store can't be abused as a PII dump.
MAX_PROPERTIES_KEYS = 64
MAX_PROPERTY_LEN = 256


class Event(models.Model):
    """One captured product event (page view, booking requested, ...)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_events",
    )
    event = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=32, blank=True, default="")
    properties = models.JSONField(default=dict, blank=True)
    session_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    path = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.event} @ {self.created_at:%Y-%m-%d %H:%M}"
