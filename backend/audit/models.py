"""Audit-log domain model.

A single append-only table recording *who did what to which object* for
sensitive actions (fraud report reviews, 2FA toggles, admin decisions).
Append-only by convention — entries are never updated or deleted in normal
operation — so an audit trail cannot be silently rewritten.
"""

from django.conf import settings
from django.db import models


class AuditLogEntry(models.Model):
    """One immutable record of a sensitive action."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor_id or 'system'} @ {self.created_at:%Y-%m-%d %H:%M}"
