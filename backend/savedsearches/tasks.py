"""Celery tasks — saved-search AI matching (Phase 11+).

Two complementary paths, both sharing the same scored/deduped matcher:

- ``match_room_event`` — fired from a Room post-save signal: a brand-new room
  is scored against every active user's saved searches and relevant matches
  are alerted immediately; a *price change* on an existing room triggers
  price-drop alerts for matching saved searches.
- ``check_saved_searches`` — the daily beat digest (kept as a safety net):
  rooms that arrived since the last check are scored and alerted, skipping
  anything already notified (cooldown dedupe via ``Notification.meta``).

With no broker configured (local dev/CI) tasks run eagerly/synchronously;
with Redis they're fully async — matching never blocks room creation either
way (the dispatch is wrapped defensively).
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _market_stats():
    from pricing.models import MarketStat

    return {(stat.area, stat.room_type): stat for stat in MarketStat.objects.all()}


@shared_task
def match_room_event(room_id: int, created: bool) -> dict:
    """Score a room event (create or price change) against saved searches.

    ``created=False`` rooms only produce notifications when their price
    dropped materially (price-drop alert); ``created=True`` rooms are scored
    for relevance. Hard filters always gate; cooldown dedupes repeats.
    """
    from django.conf import settings

    from rooms.models import Room

    from .models import SavedSearch
    from .services import latest_price_drop, notify_saved_search_match, score_saved_search_match

    if not getattr(settings, "SAVED_SEARCH_AI_MATCHING_ENABLED", True):
        return {"searches": 0, "notified": 0}

    try:
        room = Room.objects.select_related("owner").get(pk=room_id)
    except Room.DoesNotExist:
        return {"searches": 0, "notified": 0}

    from datetime import timedelta

    from django.utils import timezone

    market_stats = _market_stats()
    since = timezone.now() - timedelta(hours=24)
    price_drop = latest_price_drop(room, since=since)

    # A non-created room with no price drop has nothing new to say.
    if not created and price_drop is None:
        return {"searches": 0, "notified": 0}

    notified = 0
    for saved_search in SavedSearch.objects.select_related("user").filter(user__is_active=True):
        score_result = (
            score_saved_search_match(saved_search, room, market_stats=market_stats)
            if created
            else None
        )
        if score_result is None and not created:
            # Price-drop alerts still need the room to pass hard filters.
            from .services import apply_saved_filters

            passed = apply_saved_filters(
                Room.objects.filter(pk=room.pk), saved_search.filters
            ).exists()
            if not passed:
                continue
        if notify_saved_search_match(
            saved_search, room, score_result=score_result, price_drop=price_drop
        ):
            notified += 1

    if notified:
        logger.info("Saved-search matcher: room %s -> %d notification(s)", room_id, notified)
    return {"searches": SavedSearch.objects.count(), "notified": notified}


@shared_task
def check_saved_searches() -> dict:
    """Daily digest: alert each user about rooms matching their saved searches
    since the last check. Runs via Celery beat; ``last_checked_at`` + the
    per-room cooldown dedupe prevent repeat alerts."""
    from django.utils import timezone

    from .models import SavedSearch
    from .services import find_new_matches, notify_saved_search_match, score_saved_search_match

    checked = 0
    alerted = 0
    now = timezone.now()

    market_stats = _market_stats()
    for saved_search in SavedSearch.objects.select_related("user"):
        matches = find_new_matches(saved_search)
        saved_search.last_checked_at = now
        saved_search.save(update_fields=["last_checked_at"])
        checked += 1
        if not matches:
            continue

        for room in matches:
            score_result = score_saved_search_match(saved_search, room, market_stats=market_stats)
            if score_result is None or score_result["level"] is None:
                continue
            if notify_saved_search_match(saved_search, room, score_result=score_result):
                alerted += 1

    logger.info("Saved-search digest: checked %d search(es), %d alert(s)", checked, alerted)
    return {"checked": checked, "alerted": alerted}


@shared_task
def send_saved_search_digests() -> dict:
    """Daily **email** digest (Tier-1 quick win).

    One branded summary email per user when any of their saved searches
    matched new listings since the last digest — complementary to the in-app
    notifications above. It tracks its own cursor (``SavedSearch.digest_sent_at``)
    so the email and in-app channels each surface the same new rooms without
    one stealing the other's matches.

    Delivery goes through ``send_alert_email``, so the existing daily budget +
    failure backoff guards apply and every send is recorded in the delivery
    ledger. Users can opt out per-account (``User.digest_emails_enabled``).
    """
    from django.conf import settings
    from django.utils import timezone

    from notifications.email_guard import send_alert_email
    from notifications.models import EmailDeliveryLog

    from .models import SavedSearch
    from .services import find_new_matches

    if not getattr(settings, "SAVED_SEARCH_AI_MATCHING_ENABLED", True):
        return {"users": 0, "emailed": 0}

    now = timezone.now()
    # user_id -> {"user": ..., "rooms": {room_id: Room}} — one email per user,
    # matches deduped across all of their saved searches.
    per_user: dict[int, dict] = {}

    searches = (
        SavedSearch.objects.select_related("user")
        .filter(
            user__is_active=True,
            user__digest_emails_enabled=True,
        )
        .exclude(user__email="")
        .order_by("user_id")
    )
    for saved_search in searches:
        matches = find_new_matches(saved_search, since=saved_search.digest_sent_at)
        saved_search.digest_sent_at = now
        saved_search.save(update_fields=["digest_sent_at"])
        if not matches:
            continue
        entry = per_user.setdefault(saved_search.user_id, {"user": saved_search.user, "rooms": {}})
        for room in matches:
            if room.owner_id != saved_search.user_id:
                entry["rooms"][room.id] = room

    emailed = 0
    for entry in per_user.values():
        rooms = list(entry["rooms"].values())[:8]
        if not rooms:
            continue
        log = send_alert_email(
            subject=f"{len(rooms)} new listing(s) match your saved searches",
            to_email=entry["user"].email,
            template_name="saved_search_digest",
            context={
                "user": entry["user"],
                "rooms": rooms,
                "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:3000"),
            },
        )
        if log.status == EmailDeliveryLog.Status.SENT:
            emailed += 1

    logger.info(
        "Saved-search email digest: %d user(s) with matches, %d email(s) sent",
        len(per_user),
        emailed,
    )
    return {"users": len(per_user), "emailed": emailed}
