"""Price-prediction abstraction.

The monetization layer deliberately does *not* import pricing internals
everywhere. Instead, ``price_prediction_for`` is the single funnel that
decides which flavour of prediction a user may consume, keeping the pricing
domain pluggable (per :mod:`subscriptions.services.entitlements`) without
coupling the prediction code to the plans. This mirrors the "provider
abstraction" style of ``users.kyc_provider``.
"""

from __future__ import annotations

from .entitlements import check_entitlement, current_plan_code

# v2-only fields — withheld from the free tier of the prediction API.
_PREMIUM_FIELDS = {
    "dynamic_price",
    "demand_momentum_pct",
    "window",
    "valid_until",
    "drivers",
    "version",
}


def price_prediction_for(user, room) -> dict:
    """Full v2 prediction for entitled users; a stripped v1 for everyone else.

    The response shape stays backward compatible — the free tier still gets
    a grounded current/suggested price with direction and confidence, just
    without the dynamic-pricing premium block.
    """
    from rooms.price_recommendation import listing_price_recommendation

    result = listing_price_recommendation(room)

    if check_entitlement(user, "price_prediction_v2"):
        result["premium_unlocked"] = True
        result["plan"] = current_plan_code(user)
        return result

    stripped = {k: v for k, v in result.items() if k not in _PREMIUM_FIELDS}
    stripped["premium_unlocked"] = False
    stripped["plan"] = None
    return stripped
