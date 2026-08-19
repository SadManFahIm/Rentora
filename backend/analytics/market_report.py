"""AI Rental Market Report (Phase 15 — C6).

A weekly, deterministic digest of the rental market: per-area price levels,
demand direction, availability and a 30-day forecast, plus which areas are
rising or falling — with a Bengali plain-language summary.

Honesty contract: every number is real platform data — prices from the live
``MarketStat`` table, demand from anonymized booking/wishlist/view counts
(``forecast.area_demand``), availability from the room catalogue. Price
*movement* needs history, so the task writes a weekly ``AreaPriceSnapshot``;
the first week is honestly reported as a baseline with no movement. The
summary is generated from templates over those numbers — never invented.

The weekly task (``analytics.tasks.generate_market_report``) writes the
snapshot and emails opted-in subscribers (``User.market_report_emails_enabled``).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import AreaPriceSnapshot

# Snapshot history younger than this is ignored when computing movement — a
# report that hasn't run for months shouldn't compare against stale prices.
HISTORY_WEEKS = 26


def _week_bounds(dt=None) -> tuple[date, date]:
    """(monday, sunday) of the ISO week containing ``dt`` (default: now)."""
    today = (dt or timezone.now()).date()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _area_segments(area: str):
    from pricing.models import MarketStat

    return list(MarketStat.objects.filter(area=area))


def _weighted_average(segments, attr: str) -> float | None:
    """Weighted by sample size so big segments dominate the area number."""
    pairs = [(float(getattr(s, attr)), s.sample_size) for s in segments if s.sample_size > 0]
    if not pairs:
        return None
    total_weight = sum(w for _, w in pairs) or 1
    return sum(v * w for v, w in pairs) / total_weight


def _area_availability(area: str) -> dict:
    from rooms.models import Room

    agg = Room.objects.filter(area=area).aggregate(
        available=Count("id", filter=Q(is_available=True)),
        total=Count("id"),
    )
    total = agg["total"] or 0
    available = agg["available"] or 0
    return {
        "available_count": available,
        "total_count": total,
        "availability_pct": round(available * 100 / total) if total else 0,
    }


def _previous_week_stats(area: str, week_start: date) -> dict[str, float]:
    """Prior-week weighted area numbers from the snapshot history."""
    prior = AreaPriceSnapshot.objects.filter(
        area=area,
        week_start__lt=week_start,
        week_start__gte=week_start - timedelta(weeks=HISTORY_WEEKS),
    ).order_by("-week_start")
    latest: dict[tuple[str, str], AreaPriceSnapshot] = {}
    for row in prior:
        latest.setdefault((row.area, row.room_type), row)
    segments = list(latest.values())
    return {
        "avg": _weighted_average(segments, "avg_price"),
        "median": _weighted_average(segments, "median_price"),
    }


def _movement(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _summary_bn(areas: list[dict], week_label: str, baseline: bool) -> str:
    def bn(n):
        return str(n).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))

    if not areas:
        return "এই সপ্তাহে বিশ্লেষণের জন্য পর্যাপ্ত ডেটা নেই।"
    ranked = sorted(areas, key=lambda a: a.get("demand_index") or 0, reverse=True)
    top = ranked[0]
    parts = [f"সাপ্তাহিক বাজার রিপোর্ট — {week_label}। {bn(len(areas))}টি এলাকা বিশ্লেষিত হয়েছে।"]
    if baseline:
        parts.append(
            "এটি প্রথম সপ্তাহ — ভিত্তি (baseline) রেকর্ড করা হয়েছে; দামের পরিবর্তনের ধারা "
            "আগামী সপ্তাহ থেকে দেখানো হবে।"
        )
    if top.get("demand_index") is not None:
        parts.append(
            f"সবচেয়ে বেশি চাহিদা: {top['area']} (চাহিদা সূচক {bn(top['demand_index'])}/১০০, "
            f"প্রবণতা {top.get('direction', 'unknown')})।"
        )
    affordable = sorted([a for a in areas if a.get("avg_price")], key=lambda a: a["avg_price"])
    if affordable:
        parts.append(
            f"সবচেয়ে সাশ্রয়ী: {affordable[0]['area']} (গড় ৳{bn(round(affordable[0]['avg_price']))})।"
        )
    return " ".join(parts)


def _compute_report(persist: bool) -> dict:
    from rooms.models import Room

    from .forecast import area_demand

    week_start, week_end = _week_bounds()
    week_label = f"{week_start} to {week_end}"
    baseline = not AreaPriceSnapshot.objects.filter(week_start__lt=week_start).exists()

    # ORDER BY the projected column: SQLite's DISTINCT misbehaves when the
    # model's Meta.ordering adds hidden ORDER BY columns to the query.
    areas = list(Room.objects.order_by("area").values_list("area", flat=True).distinct())
    rows: list[dict] = []
    for area in areas:
        segments = _area_segments(area)
        avg_price = _weighted_average(segments, "avg_price")
        median_price = _weighted_average(segments, "median_price")
        availability = _area_availability(area)
        demand = area_demand(area)
        prior = _previous_week_stats(area, week_start)

        if persist and segments:
            for segment in segments:
                AreaPriceSnapshot.objects.update_or_create(
                    area=area,
                    room_type=segment.room_type,
                    week_start=week_start,
                    defaults={
                        "avg_price": segment.avg_price,
                        "median_price": segment.median_price,
                        "sample_size": segment.sample_size,
                    },
                )

        rows.append(
            {
                "area": area,
                "avg_price": round(avg_price) if avg_price is not None else None,
                "median_price": round(median_price) if median_price is not None else None,
                "sample_size": sum(s.sample_size for s in segments),
                **availability,
                "demand_index": demand.get("demand_index"),
                "direction": demand.get("direction"),
                "forecast_30d": demand.get("forecast_30d"),
                "prev_avg_price": round(prior["avg"]) if prior["avg"] is not None else None,
                "price_change_pct": _movement(avg_price, prior["avg"]),
            }
        )

    rising = [r["area"] for r in rows if r.get("direction") == "rising"]
    falling = [r["area"] for r in rows if r.get("direction") == "falling"]

    highlights: list[dict] = []
    for area in rising[:3]:
        row = next(r for r in rows if r["area"] == area)
        highlights.append(
            {
                "area": area,
                "kind": "rising",
                "text": (
                    f"Demand in {area} is rising (index {row['demand_index']}/100, "
                    f"30-day forecast +{row['forecast_30d']:.0f} signals)."
                ),
            }
        )
    for area in falling[:2]:
        row = next(r for r in rows if r["area"] == area)
        highlights.append(
            {
                "area": area,
                "kind": "falling",
                "text": f"Demand in {area} is easing (direction {row['direction']}).",
            }
        )

    return {
        "week_label": week_label,
        "as_of": timezone.now().isoformat(),
        "areas": rows,
        "rising": rising,
        "falling": falling,
        "highlights": highlights,
        "summary_bn": _summary_bn(rows, week_label, baseline),
        "baseline": baseline,
        "note": (
            "Automatic report from live MarketStat prices, anonymized demand "
            "counts and the room catalogue. Movement compares against the "
            "previous weekly snapshot; the first week is a baseline."
        ),
    }


def build_report() -> dict:
    """The latest report without mutating anything (public read path)."""
    return _compute_report(persist=False)


def generate_report() -> dict:
    """Generate + persist the weekly snapshot (task / admin path)."""
    report = _compute_report(persist=True)
    report["emails_sent"] = 0
    if getattr(settings, "MARKET_REPORT_ENABLED", True):
        report["emails_sent"] = _email_subscribers(report)
    return report


def _email_subscribers(report: dict) -> int:
    """Send the report to opted-in subscribers (landlord newsletter)."""
    from django.contrib.auth import get_user_model

    from notifications.email_guard import send_alert_email
    from notifications.models import EmailDeliveryLog

    if not report["areas"]:
        return 0

    User = get_user_model()
    users = (
        User.objects.filter(
            is_active=True,
            market_report_emails_enabled=True,
            role=User.Role.LANDLORD,
        )
        .exclude(email="")
        .order_by("id")[:500]
    )
    sent = 0
    for user in users:
        log = send_alert_email(
            subject=f"Rental Market Report — {report['week_label']}",
            to_email=user.email,
            template_name="market_report",
            context={
                "user": user,
                "report": report,
                "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:3000"),
            },
        )
        if log.status == EmailDeliveryLog.Status.SENT:
            sent += 1
    return sent
