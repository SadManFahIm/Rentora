"""Helpers for writing audit-log entries."""

from __future__ import annotations

import logging
from typing import Any

from .models import AuditLogEntry

logger = logging.getLogger(__name__)


def log_action(
    *,
    actor=None,
    action: str,
    target=None,
    request=None,
    detail: dict[str, Any] | None = None,
) -> AuditLogEntry | None:
    """Append one audit entry.

    ``target`` may be any Django model instance (its ``_meta.label`` +
    ``pk`` are recorded). ``request`` optionally provides the client IP so
    sensitive actions are traceable to a source address.

    Never raises: auditing must not take down the action it records. On a
    write failure the entry is dropped with a logged error and ``None`` is
    returned.
    """
    target_type = ""
    target_id = ""
    if target is not None:
        target_type = getattr(target._meta, "label", target.__class__.__name__)
        target_id = str(getattr(target, "pk", ""))

    ip_address = None
    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR")

    try:
        return AuditLogEntry.objects.create(
            actor=actor if actor and getattr(actor, "pk", None) else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
            ip_address=ip_address,
        )
    except Exception:
        logger.exception("Audit log write failed for action=%s", action)
        return None
