"""Listing Autopilot Celery tasks (Phase 19.3).

``run_weekly_autopilot`` is the single scheduled entrypoint. It is idempotent
by construction (per-room ``ListingAnalysis`` unique constraints + unresolved
proposal de-duplication), isolates each listing's analysis in its own
transaction (one bad room never aborts the run) and emits exactly ONE
batched notification per landlord who received new recommendations
(no-spam weekly batch).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from celery import shared_task
from django.db import transaction

from . import constants as C
from .notifications import notify_weekly_summary
from .services import analyze_and_propose, week_key

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_weekly_autopilot(self):
    """Analyze every eligible landlord listing and mint proposals for those
    with actionable recommendations.

    Returns a summary dict (room_count, analyzed, skipped, errors, landlords_notified).
    """
    from django.db.models import Q

    from rooms.models import Room

    settings_block = C.AutopilotSettings()
    if not settings_block.enabled:
        logger.info("listing autopilot disabled at settings — skipping weekly run")
        return {"enabled": False, "room_count": 0, "analyzed": 0, "skipped": 0, "errors": 0}

    week = week_key()
    if not settings_block.week_in_rollout(week):
        logger.info("week %s outside LISTING_AUTOPILOT_ROLLOUT_WEEK_KEYS — skipping", week)
        return {"enabled": True, "rollout_skipped": True, "week_key": week, "room_count": 0}

    rooms = Room.objects.filter(is_available=True).exclude(
        Q(owner__isnull=True) | Q(owner__role="tenant")
    )
    by_landlord: dict[int, list] = defaultdict(list)
    for room in rooms.iterator(chunk_size=500):
        by_landlord[room.owner_id].append(room)
    room_count = sum(len(v) for v in by_landlord.values())

    analyzed = 0
    skipped = 0
    errors = 0
    notified = 0

    for landlord_id, room_list in by_landlord.items():
        landlord = _load_landlord(landlord_id)
        if landlord is None:
            skipped += len(room_list)
            continue
        for room in room_list:
            try:
                with transaction.atomic():
                    analyze_and_propose(landlord, room, week=week)
                analyzed += 1
            except Exception:
                errors += 1
                logger.exception("autopilot analysis failed for room %s", room.pk)
                continue
        # One batched digest per landlord when they have new recommendations.
        try:
            from .notifications import landlord_digest

            digest = landlord_digest(landlord, week=week)
            if digest.get("total", 0) > 0:
                notify_weekly_summary(landlord, week=week, digest=digest)
                notified += 1
        except Exception:
            logger.exception("autopilot digest failed for landlord %s", landlord_id)

    logger.info(
        "autopilot weekly run: rooms=%s analyzed=%s skipped=%s errors=%s notified=%s",
        room_count,
        analyzed,
        skipped,
        errors,
        notified,
    )
    return {
        "enabled": True,
        "week_key": week,
        "room_count": room_count,
        "analyzed": analyzed,
        "skipped": skipped,
        "errors": errors,
        "landlords_notified": notified,
    }


def _load_landlord(user_id: int):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(pk=user_id, role="landlord").first()
