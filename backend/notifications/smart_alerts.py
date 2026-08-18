"""Smart AI Alerts (Tier 4) — prioritization over the existing notification feed.

The notification pipeline already exists (booking/review/payment/saved-search
signals + real-time push). What was missing is *intelligence*: a user with 40
unread notifications has no idea which one matters. This service ranks the
feed with a deterministic, explainable priority score so the UI can surface
the few alerts that actually need attention.

Priorities are rule-based and type-aware (safety/financial > booking >
marketing), boosted by recency and by the saved-search matcher's own
relevance metadata (``meta.level`` / ``meta.score``) — the same grounded
score the matcher already computed. Every alert gets a plain-language
``reason`` so the ranking is auditable, not a black box.

Privacy: operates only on the requesting user's own notifications.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.utils import timezone

# Base priority per notification type (0-100). Safety and financial events
# are deliberately highest: a fraud flag or payment failure must not be
# buried under marketing.
_TYPE_PRIORITY: dict[str, int] = {
    "fraud_flag": 95,
    "kyc_sla_breach": 95,
    "account_suspended": 92,
    "account_warning": 90,
    "payment_failed": 85,
    "payment_reminder": 80,
    "payment_success": 75,
    "dispute_opened": 80,
    "dispute_update": 78,
    "booking_request": 70,
    "booking_approved": 70,
    "booking_rejected": 70,
    "booking_cancelled": 70,
    "tenant_kyc_approved": 72,
    "tenant_kyc_rejected": 72,
    "tenant_kyc_needs_review": 65,
    "saved_search_match": 55,  # boosted below by matcher relevance
    "roommate_request": 62,
    "roommate_approved": 60,
    "new_review": 52,
    "content_moderated": 50,
    "report_resolved": 50,
    "new_message": 48,
    "system": 30,
}

RECENCY_HOURS_HIGH = 1
RECENCY_HOURS_MED = 24
RECENCY_BOOST_HIGH = 12
RECENCY_BOOST_MED = 5
MATCH_HIGHLY_RELEVANT_BOOST = 15
MATCH_SCORE_BOOST = 10


def priority_for(notification) -> tuple[int, str]:
    """(score, reason) for one notification — the explainable ranking."""
    ntype = notification.notification_type
    base = _TYPE_PRIORITY.get(ntype, 35)
    reasons: list[str] = []

    # Saved-search matches carry the matcher's own relevance level/score.
    if ntype == "saved_search_match":
        meta = notification.meta or {}
        level = str(meta.get("level", "")).lower()
        score = meta.get("score")
        if level in ("highly_relevant", "strong", "high") or (
            isinstance(score, (int, float)) and score >= 75
        ):
            base += MATCH_HIGHLY_RELEVANT_BOOST
            reasons.append("highly relevant match")
        elif isinstance(score, (int, float)) and score >= 60:
            base += MATCH_SCORE_BOOST
            reasons.append("strong match score")

    # Recency: fresh alerts demand attention now.
    age = timezone.now() - notification.created_at
    if age <= timedelta(hours=RECENCY_HOURS_HIGH):
        base += RECENCY_BOOST_HIGH
        reasons.append("just arrived")
    elif age <= timedelta(hours=RECENCY_HOURS_MED):
        base += RECENCY_BOOST_MED
        reasons.append("from today")

    score = max(0, min(100, base))
    if not reasons:
        reasons.append("routine update")
    return score, ", ".join(reasons[:2])


def rank_alerts(notifications: Iterable[Any]) -> list[dict[str, Any]]:
    """Rank a queryset/iterable of notifications by priority (desc).

    Returns lightweight dicts (id, priority, reason, type) that the endpoint
    merges with the full serialized notifications — the serializer stays the
    single source of shape.
    """
    ranked = [
        {
            "id": n.id,
            "priority": priority_for(n)[0],
            "reason": priority_for(n)[1],
            "notification_type": n.notification_type,
            "is_read": n.is_read,
        }
        for n in notifications
    ]
    ranked.sort(key=lambda r: r["priority"], reverse=True)
    return ranked
