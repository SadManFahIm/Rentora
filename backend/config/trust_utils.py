"""Shared trust/safety utilities for Phase 17 (Stage 2).

Provides:

- ``is_admin_user(user)``: consistent admin/staff permission check used
  across fraud, KYC, review moderation, and graph endpoints.
- ``log_trust_action(actor, action, target, request, detail)``: thin wrapper
  around ``audit.services.log_action`` that prefixes Phase 17 actions
  with ``trust.`` for easy filtering.
- ``compute_haversine_distance(lat1, lng1, lat2, lng2)``: distance between
  two GPS coordinates in metres (used by photo-geo, Stage 5).
"""

from __future__ import annotations

import math
from typing import Any


def is_admin_user(user) -> bool:
    """Check if a user has admin/staff privileges for trust & safety endpoints.

    Mirrors the inline ``request.user.is_staff or request.user.role == "admin"``
    check used throughout fraud/views.py. Centralised here so Phase 17
    endpoints use the same logic without repeating the pattern.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_staff or getattr(user, "role", "") == "admin")


def log_trust_action(
    *,
    actor=None,
    action: str,
    target=None,
    request=None,
    detail: dict[str, Any] | None = None,
):
    """Write a trust/fraud audit entry with the ``trust.`` prefix.

    Thin wrapper around ``audit.services.log_action`` that ensures
    Phase 17 actions are namespaced for easy filtering in the admin
    audit trail.

    Never raises — auditing must not block the action it records.
    """
    from audit.services import log_action

    return log_action(
        actor=actor,
        action=f"trust.{action}",
        target=target,
        request=request,
        detail=detail or {},
    )


def compute_haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two GPS coordinates in metres.

    Used by the photo-geo authenticity detector (Stage 5) to compare
    photo-extracted GPS against the room's declared area centroid.

    Parameters
    ----------
    lat1, lng1 : float
        First coordinate (decimal degrees).
    lat2, lng2 : float
        Second coordinate (decimal degrees).

    Returns
    -------
    float
        Distance in metres.
    """
    R = 6_371_000  # Earth's mean radius in metres
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
