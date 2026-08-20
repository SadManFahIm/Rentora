"""Analytics API: capture (any visitor) and summary (admin only)."""

from __future__ import annotations

import logging

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttling import TrustedUserRateThrottle

from .models import MAX_PROPERTIES_KEYS, MAX_PROPERTY_LEN, Event
from .services import build_summary

logger = logging.getLogger(__name__)

_EVENT_MAX_LEN = 64
_CATEGORY_MAX_LEN = 32
_SESSION_MAX_LEN = 64
_PATH_MAX_LEN = 300


class AnalyticsCaptureRateThrottle(TrustedUserRateThrottle):
    """A busy visitor can generate a lot of events — but a hard cap still
    stops a scripted flood from filling the store. Scope rate lives in
    ``DEFAULT_THROTTLE_RATES['analytics']``."""

    scope = "analytics"


def _clean_payload(data: dict) -> dict | None:
    """Validate + bound the incoming event. Returns cleaned fields or None
    when the payload is unusable (caller replies 400)."""
    event = str(data.get("event", "")).strip()[:_EVENT_MAX_LEN]
    if not event:
        return None

    properties = data.get("properties") or {}
    if not isinstance(properties, dict) or len(properties) > MAX_PROPERTIES_KEYS:
        return None
    # Bound individual values too — keeps the JSON column tidy.
    properties = {
        str(k)[:128]: (str(v)[:MAX_PROPERTY_LEN] if not isinstance(v, (int, float, bool)) else v)
        for k, v in properties.items()
    }

    return {
        "event": event,
        "category": str(data.get("category", ""))[:_CATEGORY_MAX_LEN],
        "session_id": str(data.get("session_id", ""))[:_SESSION_MAX_LEN],
        "path": str(data.get("path", ""))[:_PATH_MAX_LEN],
        "properties": properties,
    }


@extend_schema(
    tags=["Analytics"],
    summary="Capture a product event",
    description=(
        "Fire-and-forget event capture for first-party product analytics. "
        "Auth optional: authenticated users are attributed (user-scoped "
        "funnels), anonymous visitors are tracked by session_id only. "
        "Never send PII — payloads are bounded server-side."
    ),
)
class CaptureEventView(APIView):
    """POST /api/v1/analytics/events/ — record one product event."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnalyticsCaptureRateThrottle]

    def post(self, request):
        cleaned = _clean_payload(request.data)
        if cleaned is None:
            return Response(
                {"detail": "event is required; properties must be a small object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user if request.user.is_authenticated else None
        with transaction.atomic():
            Event.objects.create(user=user, **cleaned)
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Analytics"],
    summary="Analytics summary (admin)",
    description=(
        "Admin only. One snapshot of the last `?days=` (default 30): event "
        "totals, top events/pages, daily volume, and the conversion funnel "
        "(distinct authenticated users per step)."
    ),
)
class AnalyticsSummaryView(APIView):
    """GET /api/v1/analytics/summary/?days=30 — admin dashboard data."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or getattr(request.user, "role", "") == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        return Response(build_summary(days))


class DemandForecastView(APIView):
    """GET /api/v1/analytics/forecast/?area=Uttara — demand index + 30-day trend.

    Public: demand is estimated from anonymized *counts* (bookings, wishlist
    saves, listing views) — no PII, no individual user data. Omit ``area``
    for the full per-area snapshot.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .forecast import area_demand, area_demand_summary

        area = request.query_params.get("area", "").strip()
        if area:
            return Response(area_demand(area))
        return Response(area_demand_summary())


@extend_schema(
    tags=["Analytics"],
    summary="Rental market report (public)",
    description=(
        "Public, read-only. The weekly per-area market digest: current prices, "
        "demand direction, 30-day forecast, availability and price movement "
        "versus the previous weekly snapshot. The first week is a baseline "
        "(`baseline: true`) with no movement."
    ),
)
class MarketReportView(APIView):
    """GET /api/v1/analytics/market-report/ — the latest market digest."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .market_report import build_report

        return Response(build_report())


@extend_schema(
    tags=["Analytics"],
    summary="Generate market report now (admin)",
    description=(
        "Admin only. Writes this week's price snapshot and emails opted-in "
        "subscribers immediately. Normally the weekly Celery beat task does "
        "this on Monday mornings."
    ),
)
class MarketReportGenerateView(APIView):
    """POST /api/v1/analytics/market-report/generate/ — admin trigger."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not (request.user.is_staff or getattr(request.user, "role", "") == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from .market_report import generate_report

        report = generate_report()
        return Response(
            {
                "ok": True,
                "week_label": report["week_label"],
                "areas": len(report["areas"]),
                "baseline": report["baseline"],
                "subscribed_emails": report.get("emails_sent", 0),
            }
        )
