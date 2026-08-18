"""Tier-4 advisory engines — deterministic, data-grounded helpers.

Like the rest of the Copilot, these are **rule-based and grounded in real
database rows** — no LLM is called anywhere. Every number quoted in advice
(area averages, market percentiles, demand levels) comes from ``MarketStat``
or the live ``Room`` table, so the assistant can never invent a price,
area or comparison.

Four engines live here:

1. **Rental Advisor** — ``rental_advice``. Given a tenant's budget and
   optional constraints, recommend affordable areas (median rent fits the
   budget), flag the classic rent-to-income rule (≤30%), and return a
   practical move-in checklist. Honest by design: when an area's market is
   too thin to compare, it says so instead of guessing.
2. **Negotiation Assistant** — ``negotiation_draft``. Drafts a negotiation
   message for the tenant or landlord. The offer is compared against the
   area/room-type market (median + percentile 25) so the draft's number is
   a *grounded* counter-offer, not a random discount.
3. **Agreement Checker** — ``agreement_check``. Scans a rental-agreement
   text against a bilingual clause dictionary (notice period, deposit,
   rent-increase, maintenance, termination, sublet) and flags risky /
   missing clauses with plain-language explanations.
4. **Landlord Copilot** — ``landlord_insights``. Answers a landlord's
   question about **their own listing** using the room's real booking,
   wishlist and market data ("why isn't my room getting bookings?" →
   price vs area average, photo count, description length, demand level).

Privacy: engine 4 only ever reads the requesting landlord's own rooms (the
caller enforces ownership); engines 1-3 use only public listing / market
aggregates.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from rooms.models import Room

# ---------------------------------------------------------------------------
# Shared market helpers
# ---------------------------------------------------------------------------


def _market_stats_map():
    """{(area, room_type): MarketStat} — one query, reused across engines."""
    from pricing.models import MarketStat

    return {(stat.area, stat.room_type): stat for stat in MarketStat.objects.all()}


def _price_float(room: Room) -> float:
    return float(room.price or 0)


def _affordability(monthly_income: float, rent: float) -> dict[str, Any]:
    """Classic rent-to-income rule, honestly labelled as guidance."""
    ratio = (rent / monthly_income) if monthly_income > 0 else None
    if ratio is None:
        level, hint = "unknown", "Share your monthly income for a rent-budget check."
    elif ratio <= 0.3:
        level, hint = "comfortable", "Rent is within the common 30% guideline."
    elif ratio <= 0.4:
        level, hint = "tight", "Rent is above the 30% guideline — expect a tight budget."
    else:
        level, hint = "high", "Rent is well above the 30% guideline — consider cheaper areas."
    return {"ratio": round(ratio, 2) if ratio is not None else None, "level": level, "hint": hint}


# ---------------------------------------------------------------------------
# 1. AI Rental Advisor
# ---------------------------------------------------------------------------

_AREA_LABELS: dict[str, str] = {
    "Uttara": "Uttara (north — airport access, many job hubs)",
    "Dhanmondi": "Dhanmondi (central, student-friendly)",
    "Mirpur": "Mirpur (mid-budget, family-friendly)",
    "Gulshan": "Gulshan (premium, embassy zone)",
    "Banani": "Banani (premium, offices nearby)",
    "Bashundhara": "Bashundhara (mid, growing student hub)",
    "Mohammadpur": "Mohammadpur (budget, well-connected)",
    "Tejgaon": "Tejgaon (business district, mid)",
    "Badda": "Badda (mid, office corridor)",
    "Khilgaon": "Khilgaon (budget, transit-heavy)",
    "Old Dhaka": "Old Dhaka (budget, traditional market)",
    "Shyamoli": "Shyamoli (mid-budget)",
}


def rental_advice(
    budget_max: float,
    room_type: str = "single",
    area: str = "",
    monthly_income: float | None = None,
) -> dict[str, Any]:
    """Recommend areas whose median rent fits ``budget_max`` (AI Rental Advisor).

    Grounded in ``MarketStat`` medians for the requested room type. Returns
    recommendations sorted by how far under budget each area sits, plus an
    affordability check and a move-in checklist.
    """
    market = _market_stats_map()
    rooms_qs = Room.objects.filter(is_available=True)
    if room_type:
        rooms_qs = rooms_qs.filter(room_type=room_type)

    candidates: list[dict[str, Any]] = []
    seen_areas: set[str] = set()
    if area:
        seen_areas.add(area)
        stat = market.get((area, room_type))
        if stat:
            candidates.append(
                {
                    "area": area,
                    "label": _AREA_LABELS.get(area, area),
                    "median_rent": float(stat.median_price),
                    "sample_size": stat.sample_size,
                    "source": "market_stat",
                }
            )
        else:
            candidates.append(
                {
                    "area": area,
                    "label": _AREA_LABELS.get(area, area),
                    "median_rent": None,
                    "sample_size": 0,
                    "source": "requested",
                }
            )

    # Fill with the best-fit areas from live listings when stats are thin.
    for stat in sorted(
        (s for (a, rt), s in market.items() if rt == room_type and a not in seen_areas),
        key=lambda s: float(s.median_price),
    ):
        if float(stat.median_price) > budget_max:
            continue
        candidates.append(
            {
                "area": stat.area,
                "label": _AREA_LABELS.get(stat.area, stat.area),
                "median_rent": float(stat.median_price),
                "sample_size": stat.sample_size,
                "source": "market_stat",
            }
        )
        seen_areas.add(stat.area)

    candidates.sort(key=lambda c: (c["median_rent"] is None, c.get("median_rent") or 0))

    # Live supply per area (available rooms in budget) — real demand-side signal.
    in_budget = rooms_qs.filter(price__lte=budget_max)
    supply: dict[str, int] = {}
    for row in in_budget.values("area").annotate(n=Count("id")):
        supply[row["area"]] = row["n"]

    recommendations = [
        {
            **c,
            "available_in_budget": supply.get(c["area"], 0),
            "fits_budget": c["median_rent"] is not None and c["median_rent"] <= budget_max,
        }
        for c in candidates
    ]

    affordability = (
        _affordability(monthly_income, budget_max)
        if monthly_income
        else {"level": "unknown", "ratio": None, "hint": ""}
    )

    checklist = [
        "Verify the landlord (✓ identity badge) before paying anything.",
        "Visit the room in person — never pay advance rent sight-unseen.",
        "Get the rental agreement checked (Copilot → Agreement Checker).",
        "Confirm who pays utilities (gas, electricity, internet) in writing.",
        "Use Rentora's security-deposit flow — never hand cash directly.",
    ]

    return {
        "budget_max": budget_max,
        "room_type": room_type,
        "affordability": affordability,
        "recommendations": recommendations,
        "checklist": checklist,
    }


# ---------------------------------------------------------------------------
# 2. AI Negotiation Assistant
# ---------------------------------------------------------------------------

_NEGOTIATION_REASONS = {
    "above_market": "The listing is above the area's median for this room type.",
    "below_market": "The listing is already below the area median — a large cut is unlikely.",
    "at_market": "The listing sits near the area median.",
}


def negotiation_draft(
    room: Room,
    target_price: float | None = None,
    role: str = "tenant",
    tone: str = "polite",
) -> dict[str, Any]:
    """Draft a grounded negotiation message for ``room`` (AI Negotiation Assistant).

    ``target_price`` is optional — when omitted, the suggested offer is the
    max(percentile-25 of the area market, 10% below listing). The draft is
    always produced in both English and Bangla, with the market reasoning the
    sender can honestly quote.
    """
    market = _market_stats_map().get((room.area, room.room_type))
    listing_price = _price_float(room)

    if market and float(market.percentile_25) > 0:
        p25 = float(market.percentile_25)
        median = float(market.median_price)
        suggested = max(p25, listing_price * 0.9)
        if listing_price <= median:
            reason_key = "below_market"
        elif listing_price <= float(market.percentile_75):
            reason_key = "at_market"
        else:
            reason_key = "above_market"
    else:
        suggested = listing_price * 0.9
        median = None
        reason_key = "above_market" if listing_price > 0 else "at_market"

    offer = float(target_price) if target_price else round(suggested, -2)
    reason = _NEGOTIATION_REASONS[reason_key]
    suggested_offer = offer

    tone_prefix = {
        "polite": "I hope this message finds you well.",
        "friendly": "Hello! I really like your listing.",
        "formal": "Dear landlord,",
    }.get(tone, "I hope this message finds you well.")

    if role == "tenant":
        en_body = (
            f"{tone_prefix} I'm interested in your room '{room.title}' listed at ৳{listing_price:,.0f}. "
            f"Would you consider ৳{offer:,.0f}/month? {reason} "
            "I'm a verified tenant and ready to move in as soon as we agree."
        )
        bn_body = (
            f"{tone_prefix} আপনার '{room.title}' রুমটি (ভাড়া ৳{listing_price:,.0f}) আমার পছন্দ হয়েছে। "
            f"মাসে ৳{offer:,.0f} হলে কি বিবেচনা করবেন? {reason} "
            "আমি যাচাইকৃত (verified) ভাড়াটিয়া, চুক্তি হলে সাথে সাথে উঠতে পারব।"
        )
    else:
        en_body = (
            f"{tone_prefix} Thank you for your interest in '{room.title}' (৳{listing_price:,.0f}/month). "
            f"I can offer ৳{offer:,.0f}/month for a long-term stay. {reason}"
        )
        bn_body = (
            f"{tone_prefix} '{room.title}' (৳{listing_price:,.0f}/মাস) আগ্রহের জন্য ধন্যবাদ। "
            f"দীর্ঘমেয়াদি থাকার জন্য মাসে ৳{offer:,.0f} দিতে পারি। {reason}"
        )

    return {
        "listing_id": room.id,
        "listing_price": listing_price,
        "suggested_offer": round(suggested_offer, 0),
        "market_median": median,
        "reason": reason,
        "draft_en": en_body,
        "draft_bn": bn_body,
    }


# ---------------------------------------------------------------------------
# 3. AI Rental Agreement Checker
# ---------------------------------------------------------------------------

# clause -> (risk, explanation) — bilingual keyword sets.
_AGREEMENT_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...], str, str]] = [
    (
        "notice_period",
        ("notice", "notice period", "notice of", "দিনের নোটিশ", "নোটিশ"),
        (r"\bnotice\b", r"দিনের নোটিশ", r"নোটিশ"),
        "info",
        "Notice period mentioned — check it is reasonable (typically 1-2 months in Dhaka).",
    ),
    (
        "deposit",
        ("deposit", "security deposit", "সিকিউরিটি ডিপোজিট", "ডিপোজিট", "জামানত"),
        (r"deposit", r"জামানত", r"ডিপোজিট"),
        "info",
        "Deposit clause found — ensure the refund terms and any deduction rules are stated.",
    ),
    (
        "rent_increase",
        ("rent increase", "increase", "increment", "ভাড়া বৃদ্ধি", "ভাড়া বাড়বে", "ইনক্রিমেন্ট"),
        (r"increase", r"বৃদ্ধি", r"বাড়বে", r"ইনক্রিমেন্ট"),
        "warn",
        "Rent-increase clause present — confirm the % and frequency are defined.",
    ),
    (
        "maintenance",
        ("maintenance", "repair", "মেরামত", "রক্ষণাবেক্ষণ"),
        (r"maintenance", r"repair", r"মেরামত", r"রক্ষণাবেক্ষণ"),
        "warn",
        "Maintenance responsibility should be explicit — who pays for repairs?",
    ),
    (
        "termination",
        ("termination", "terminate", "cancel", "বাতিল", "বাতিলকরণ"),
        (r"terminat", r"cancel", r"বাতিল"),
        "warn",
        "Termination clause found — confirm the exit terms and penalties.",
    ),
    (
        "sublet",
        ("sublet", "sub-let", "sublease", "উপ-ভাড়া", "সাবলেট"),
        (r"sublet", r"sub-let", r"sublease", r"সাবলেট"),
        "info",
        "Subletting mentioned — know whether guests/sublet are allowed.",
    ),
]


def agreement_check(text: str) -> dict[str, Any]:
    """Scan a rental-agreement text for risky or missing clauses.

    Returns a verdict (``review`` when any warn-level risk is found, else
    ``looks_ok`` with the caveat that this is not legal advice), the detected
    clauses with plain-language explanations, and a list of clauses that were
    *not* found so the user can ask the landlord for them.
    """
    text = (text or "").strip()
    if not text:
        return {
            "verdict": "empty",
            "risk_level": "info",
            "clauses": [],
            "missing": [],
            "disclaimer": "Paste your agreement text for an automated first-pass review.",
        }

    found: list[dict[str, Any]] = []
    for key, _kw, _rx, risk, explanation in _AGREEMENT_RULES:
        if any(re.search(rx, text, re.IGNORECASE) for rx in _rx):
            found.append({"clause": key, "risk": risk, "explanation": explanation})

    missing = [
        key
        for key, _kw, _rx, _risk, _exp in _AGREEMENT_RULES
        if key not in {f["clause"] for f in found}
    ]

    has_warn = any(f["risk"] == "warn" for f in found)
    verdict = "review" if has_warn else "looks_ok"
    risk_level = "warn" if has_warn else "info"

    return {
        "verdict": verdict,
        "risk_level": risk_level,
        "clauses": found,
        "missing": missing,
        "disclaimer": "Automated first-pass review only — not legal advice. Have a lawyer review before signing.",
    }


# ---------------------------------------------------------------------------
# 4. Landlord Copilot
# ---------------------------------------------------------------------------

_INSIGHT_LOOKBACK_DAYS = 30


def landlord_insights(room: Room) -> dict[str, Any]:
    """Grounded analysis of one listing for its owner (Landlord Copilot).

    Reads only public market stats plus the room's own booking / wishlist /
    review counts — never other tenants' data. The answer is a structured
    diagnosis: how the price compares to the area, listing-quality signals,
    recent interest (bookings + wishlist saves) and concrete suggestions.
    """
    market = _market_stats_map().get((room.area, room.room_type))
    listing_price = _price_float(room)

    price_compare: dict[str, Any] = {"listing_price": listing_price}
    if market and market.sample_size >= 3:
        median = float(market.median_price)
        price_compare.update(
            {
                "market_median": median,
                "percentile_25": float(market.percentile_25),
                "percentile_75": float(market.percentile_75),
                "position": (
                    "below_market"
                    if listing_price < median * 0.95
                    else "above_market"
                    if listing_price > median * 1.05
                    else "at_market"
                ),
            }
        )
    else:
        price_compare["market_median"] = None

    since = timezone.now() - timedelta(days=_INSIGHT_LOOKBACK_DAYS)
    interest = {
        "bookings": room.bookings.filter(created_at__gte=since).count(),
        "wishlist_saves": room.wishlisted_by.filter(created_at__gte=since).count(),
        "reviews": getattr(room, "reviews", None).count() if hasattr(room, "reviews") else 0,
    }

    quality = None
    if getattr(settings, "LISTING_QUALITY_SCORE_ENABLED", True):
        from rooms.listing_quality import get_listing_quality

        quality = get_listing_quality(room, market_stats=_market_stats_map())

    suggestions: list[str] = []
    if price_compare.get("position") == "above_market" and market:
        suggestions.append(
            f"Price is above the {room.area} median (৳{price_compare['market_median']:,.0f}) — consider a small cut or added value to win bookings."
        )
    if quality and quality.get("score") is not None and quality["score"] < 60:
        suggestions.extend(quality.get("suggestions", [])[:3])
    if interest["bookings"] == 0 and interest["wishlist_saves"] == 0:
        suggestions.append(
            "No bookings or saves in the last 30 days — check photos and description completeness."
        )

    return {
        "listing_id": room.id,
        "title": room.title,
        "price_compare": price_compare,
        "interest_30d": interest,
        "quality": quality,
        "suggestions": suggestions[:4],
    }
