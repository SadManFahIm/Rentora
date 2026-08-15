"""Matching logic for saved searches — shared by the API, the beat task and
the room-event task (Phase 11+ — AI saved-search matcher).

Matching is a two-stage pipeline:

1. **Hard filters** — the saved search's explicit constraints (area, budget,
   room type, gender, verified, query text). A room that violates ANY hard
   constraint never matches, no matter how semantically similar it is.
2. **Soft relevance score** — a weighted blend of area / price / room-type /
   semantic / user-preference / listing-quality components (weights in
   ``SAVED_SEARCH_MATCH_WEIGHTS``). Only rooms scoring at least
   ``SAVED_SEARCH_MATCH_THRESHOLD`` produce a notification, with a plain-
   language "why it matched" reason list.

Price-drop intelligence rides on ``RoomPriceHistory`` (written by the rooms
post-save signal): when a room's price falls by at least
``PRICE_DROP_NOTIFICATION_THRESHOLD`` since the last check, matching saved
searches are alerted even if the room itself isn't new. A cooldown
(``SAVED_SEARCH_COOLDOWN_HOURS``, tracked via ``Notification.meta``) prevents
re-notifying the same user about the same room on every scan.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from rooms.models import Room
from rooms.search import search_rooms

_ALLOWED_FILTERS = {
    "area": "area",
    "room_type": "room_type",
    "gender_preference": "gender_preference",
}


def apply_saved_filters(queryset, filters: dict[str, Any]):
    """Apply a saved search's filter dict to a Room queryset (hard filters)."""
    clause = Q()
    for key, field in _ALLOWED_FILTERS.items():
        value = filters.get(key)
        if value:
            clause &= Q(**{field: value})
    price_min = filters.get("price_min")
    price_max = filters.get("price_max")
    if price_min:
        clause &= Q(price__gte=price_min)
    if price_max:
        clause &= Q(price__lte=price_max)
    if filters.get("verified"):
        clause &= Q(verified=True)
    queryset = queryset.filter(clause)

    query_text = (filters.get("q") or "").strip()
    if query_text:
        queryset = search_rooms(queryset, query_text)
    return queryset


def find_new_matches(saved_search, queryset=None, *, since=None) -> list[Room]:
    """Rooms matching the saved search that arrived since the last check.

    ``since`` overrides the cursor for callers that track their own (the
    daily email digest uses ``digest_sent_at`` so the email and in-app
    channels never steal each other's matches). First run: only brand-new
    rooms (created within the last day) alert.
    """
    queryset = queryset if queryset is not None else Room.objects.filter(is_available=True)
    queryset = apply_saved_filters(queryset, saved_search.filters)
    if since is None:
        since = saved_search.last_checked_at or (timezone.now())
        if saved_search.last_checked_at is None:
            # First run: only brand-new rooms (created within the last day) alert.
            from datetime import timedelta

            since = timezone.now() - timedelta(days=1)
    return list(queryset.filter(created_at__gt=since).order_by("-created_at")[:10])


# ---------------------------------------------------------------------------
# Soft relevance scoring
# ---------------------------------------------------------------------------


def _query_relevance(query: str, room_id: int) -> float:
    """0..1 semantic+lexical relevance of ``room_id`` to the search's query
    text — reuses the same hybrid legs as the live search ranking."""
    if not query.strip():
        return 0.5  # no query text — neutral, doesn't drag the score down
    from rooms import embedding_service, semantic

    score = 0.0
    has_signal = False
    sem = embedding_service.semantic_scores(query, [room_id], top_k=1)
    if sem:
        has_signal = True
        score = max(score, max(float(s) for _, s in sem))
    lex = semantic.semantic_rank(query, [room_id], top_k=1)
    if lex:
        has_signal = True
        score = max(score, max(float(s) for _, s in lex))
    if not has_signal:
        return 0.5
    return max(min(score, 1.0), 0.0)


def _preference_score(user, room: Room) -> float:
    """0..1 how well the room matches the user's behavior profile; 0.5
    neutral when the user is cold-start (no profile yet)."""
    if user is None:
        return 0.5
    from recommendations.services.content_based import get_user_preference_scores

    scores = get_user_preference_scores(user, [room])
    if scores is None:
        return 0.5
    return scores.get(room.id, 0.0)


def score_saved_search_match(
    saved_search,
    room: Room,
    *,
    market_stats: dict | None = None,
    user=None,
) -> dict | None:
    """Score ``room`` against ``saved_search``.

    Returns None when a hard filter fails (never notify). Otherwise a dict:
    ``{score, level, reasons, category_scores}`` where ``level`` is one of
    ``excellent`` / ``highly_relevant`` / ``relevant`` or None when the score
    is below ``SAVED_SEARCH_MATCH_THRESHOLD``.
    """
    hard_filtered = apply_saved_filters(Room.objects.filter(pk=room.pk), saved_search.filters)
    if not hard_filtered.exists():
        return None

    weights = getattr(settings, "SAVED_SEARCH_MATCH_WEIGHTS", {})
    filters = saved_search.filters

    # ---- per-component scores (0..1) ----
    category: dict[str, float] = {}

    pref_area = filters.get("area")
    if pref_area:
        # Area aliases: a saved "Dhanmondi" search still matches a room whose
        # area is the canonical value after alias resolution.
        from rooms.area_aliases import resolve_area

        if room.area == pref_area:
            category["area"] = 1.0
        elif resolve_area(room.area) == resolve_area(pref_area):
            category["area"] = 0.9
        else:
            category["area"] = 0.0
    else:
        category["area"] = 0.5

    has_price_bound = bool(filters.get("price_min") or filters.get("price_max"))
    category["price"] = 1.0 if has_price_bound else 0.5

    pref_type = filters.get("room_type")
    if pref_type:
        category["room_type"] = 1.0 if room.room_type == pref_type else 0.0
    else:
        category["room_type"] = 0.5

    query_text = (filters.get("q") or "").strip()
    category["semantic"] = _query_relevance(query_text, room.id)

    category["preference"] = _preference_score(user or saved_search.user, room)

    from rooms.listing_quality import get_listing_quality

    quality = get_listing_quality(room, market_stats)
    category["quality"] = (quality.get("score") or 0) / 100.0

    total = round(sum(weights.get(cat, 0) * score for cat, score in category.items()), 3)
    threshold = float(getattr(settings, "SAVED_SEARCH_MATCH_THRESHOLD", 0.75))

    level = None
    if total >= 0.95:
        level = "excellent"
    elif total >= 0.85:
        level = "highly_relevant"
    elif total >= threshold:
        level = "relevant"

    return {
        "score": total,
        "level": level,
        "reasons": _build_reasons(saved_search, room, category, quality),
        "category_scores": {k: round(v, 3) for k, v in category.items()},
    }


def _build_reasons(
    saved_search, room: Room, category: dict[str, float], quality: dict
) -> list[str]:
    """Plain-language, user-safe reasons (never raw scores)."""
    reasons: list[str] = []
    filters = saved_search.filters
    if filters.get("area") and category.get("area", 0) >= 0.9:
        reasons.append(f"Matches your preferred area: {filters['area']}")
    if filters.get("price_min") or filters.get("price_max"):
        reasons.append("Within your budget")
    if filters.get("room_type") and category.get("room_type", 0) >= 1:
        reasons.append(f"Matches your preferred room type: {room.get_room_type_display()}")
    if (filters.get("q") or "").strip() and category.get("semantic", 0) >= 0.5:
        reasons.append("Highly relevant to your search query")
    if category.get("preference", 0) >= 0.5:
        reasons.append("Similar to rooms you previously viewed or saved")
    if (quality.get("score") or 0) >= 75:
        reasons.append("Well-completed listing")
    return reasons


# ---------------------------------------------------------------------------
# Price-drop detection
# ---------------------------------------------------------------------------


def latest_price_drop(room: Room, since=None) -> float | None:
    """Fractional price drop (0..1) of the most recent change, or None.

    Uses the last two ``RoomPriceHistory`` rows (written only on real price
    changes), so it never compares against a stale row or a no-op save.
    """
    from rooms.models import RoomPriceHistory

    history = list(RoomPriceHistory.objects.filter(room=room).order_by("-id")[:2])
    if len(history) < 2:
        return None
    previous, current = history[1], history[0]
    if since is not None and current.changed_at < since:
        return None
    if float(previous.price) <= 0:
        return None
    drop = (float(previous.price) - float(current.price)) / float(previous.price)
    return drop if drop > 0 else None


# ---------------------------------------------------------------------------
# Notification dispatch (shared by event task + daily digest, deduped)
# ---------------------------------------------------------------------------


def _already_notified(user, room_id: int) -> bool:
    """Has this user been alerted about this room within the cooldown window?"""
    from datetime import timedelta

    from notifications.models import Notification

    hours = int(getattr(settings, "SAVED_SEARCH_COOLDOWN_HOURS", "24"))
    cutoff = timezone.now() - timedelta(hours=hours)
    return Notification.objects.filter(
        user=user,
        notification_type=Notification.Type.SAVED_SEARCH_MATCH,
        meta__room_id=room_id,
        created_at__gte=cutoff,
    ).exists()


def notify_saved_search_match(
    saved_search, room: Room, *, score_result: dict | None, price_drop: float | None = None
) -> bool:
    """Create the saved-search notification for ``room`` if it's relevant and
    not a duplicate. Returns True when a notification was created."""
    if not getattr(settings, "SAVED_SEARCH_AI_MATCHING_ENABLED", True):
        return False
    from notifications.models import Notification
    from notifications.utils import create_notification

    user = saved_search.user
    if room.owner_id == user.id:
        return False  # never alert someone about their own listing

    matched = score_result is not None and score_result["level"] is not None
    drop = price_drop is not None and price_drop >= float(
        getattr(settings, "PRICE_DROP_NOTIFICATION_THRESHOLD", 0.10)
    )
    if not matched and not drop:
        return False
    if _already_notified(user, room.id):
        return False

    area = saved_search.filters.get("area") or room.area
    if drop:
        title = f"Price dropped in {saved_search.name}"
        percent = round(price_drop * 100)
        lines = [f"Price dropped by {percent}% — this room matches your saved search."]
        if score_result and score_result["level"]:
            lines.extend(f"✓ {reason}" for reason in score_result["reasons"])
        message = "\n".join(lines)
        level = score_result["level"] if score_result else "relevant"
    else:
        level = score_result["level"]
        prefix = {
            "excellent": "Excellent match",
            "highly_relevant": "Highly relevant room",
            "relevant": "Relevant room",
        }.get(level, "New room")
        title = f"{prefix} found in {area}"
        lines = [f"New listing: {room.title}"]
        lines.extend(f"✓ {reason}" for reason in score_result["reasons"])
        message = "\n".join(lines)

    create_notification(
        user=user,
        notification_type=Notification.Type.SAVED_SEARCH_MATCH,
        title=title,
        message=message,
        action_url=f"/rooms/{room.id}",
        meta={
            "room_id": room.id,
            "saved_search_id": saved_search.id,
            "level": level,
            "match_score": score_result["score"] if score_result else None,
        },
    )
    return True
