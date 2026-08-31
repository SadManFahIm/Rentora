"""Listing Autopilot notifications (Phase 19.3).

Deliberately minimal: the spec's "no-spam weekly batch" means the landlord gets
exactly ONE notification per weekly run (a digest of the new recommendations),
not one per proposal and not one per apply. Failure digests ride along in the
same batch so we never pester the landlord about a background worker hiccup.
All messages route through ``notifications.utils.create_notification`` (the
single sanitized entry point with WebSocket push).
"""

from __future__ import annotations

from django.db.models import Count

from . import constants as C
from .services import week_key


def landlord_digest(landlord, *, week: str = "") -> dict[str, int]:
    """Count pending autopilot proposals for one landlord in a week (no spam:
    numbers only, no per-proposal rows)."""
    from agents.models import AgentProposal

    week = week or week_key()
    rows = (
        AgentProposal.objects.filter(
            run__conversation__user=landlord,
            run__conversation__agent__key=C.AGENT_KEY,
            meta__week_key=week,
            status="pending",
        )
        .values("proposal_type")
        .annotate(count=Count("id"))
    )
    return {r["proposal_type"]: r["count"] for r in rows} | {"total": sum(r["count"] for r in rows)}


def notify_weekly_summary(
    landlord, *, week: str = "", digest: dict[str, int] | None = None
) -> None:
    """One batched notification per landlord per weekly run when there is
    something to review. Never raises (notifications must not break the run)."""
    from contextlib import suppress

    from notifications.utils import create_notification

    digest = digest or landlord_digest(landlord, week=week)
    total = digest.get("total", 0)
    if total <= 0:
        return
    types = [t for t in C.PROPOSAL_TYPES if digest.get(t)]
    with suppress(Exception):
        create_notification(
            landlord,
            "ai_alert",
            title="Listing Autopilot: recommendations ready",
            message=(
                f"{total} recommendation(s) are ready to review for your listings"
                f" (weekly batch, {week}). "
                + (", ".join(t.lower().replace("_", " ") for t in types) + ".")
            ),
            action_url="/dashboard?tab=insights",
            meta={"week_key": week, "digest": digest, "feature": C.FEATURE_ID},
        )
