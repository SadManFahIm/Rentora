"""Analytics aggregation service.

Pure-query helpers backing the admin dashboard: daily volumes, top events /
pages, and a conversion funnel. Funnel steps are product events fired by the
frontend (see ``frontend/src/services/analytics.ts``); each step counts
*distinct users* who reached it in the window, so the funnel reflects real
conversion, not raw event volume.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

# The rental conversion funnel, in order. Steps without data simply show 0 —
# the dashboard renders the full funnel shape regardless of how much of the
# product has wired events yet.
FUNNEL_STEPS = [
    "page_view",
    "room_view",
    "chat_started",
    "booking_requested",
    "booking_confirmed",
    "payment_completed",
]


def record_event(
    user,
    event: str,
    category: str = "",
    properties: dict | None = None,
    path: str = "",
    session_id: str = "",
) -> None:
    """Server-side event recording.

    The frontend emits most funnel events, but the steps that only happen on
    the server (a booking being approved, a payment completing) are recorded
    here so the funnel reflects real conversion without trusting the client.
    ``user`` may be a User or None (anonymous); never pass PII in
    ``properties`` — same bounded-payload contract as the capture endpoint.
    """
    from .models import Event

    Event.objects.create(
        user=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
        event=event,
        category=category,
        properties=properties or {},
        session_id=session_id,
        path=path,
    )


def _window(days: int):
    now = timezone.now()
    return now - timedelta(days=max(1, min(days, 90))), now


def build_summary(days: int = 30) -> dict:
    """One snapshot of the last ``days``: totals, top events/pages, daily
    volume, and the conversion funnel."""
    from django.db.models.functions import TruncDate

    from .models import Event

    start, end = _window(days)

    queryset = Event.objects.filter(created_at__gte=start, created_at__lte=end)

    totals = {
        "events": queryset.count(),
        "sessions": (queryset.exclude(session_id="").values("session_id").distinct().count()),
        "active_users": (queryset.exclude(user__isnull=True).values("user").distinct().count()),
    }

    top_events = list(queryset.values("event").annotate(count=Count("id")).order_by("-count")[:10])

    top_pages = list(
        queryset.exclude(path="").values("path").annotate(count=Count("id")).order_by("-count")[:10]
    )

    daily = [
        {"date": d.strftime("%Y-%m-%d"), "count": c}
        for d, c in queryset.annotate(date=TruncDate("created_at"))
        .values_list("date")
        .annotate(count=Count("id"))
        .order_by("date")
    ]

    # Distinct users per funnel step — user-scoped conversion. If events are
    # mostly anonymous (no auth), this under-reports; that's the honest
    # reading and we label it as such in the payload.
    funnel = OrderedDict()
    for step in FUNNEL_STEPS:
        step_users = (
            queryset.filter(event=step).exclude(user__isnull=True).values("user").distinct().count()
        )
        funnel[step] = step_users

    return {
        "days": days,
        "totals": totals,
        "top_events": top_events,
        "top_pages": top_pages,
        "daily": daily,
        "funnel": dict(funnel),
        "funnel_steps": FUNNEL_STEPS,
        "note": "Funnel counts distinct authenticated users per step.",
    }
