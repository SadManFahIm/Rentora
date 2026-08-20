"""Insurance provider abstraction.

The quote engine depends on an ``InsuranceProvider`` interface; the concrete
provider is chosen from settings (``INSURANCE_PROVIDER`` = "rule" | "http"),
exactly like ``users.kyc_provider``. The rule-based provider is deterministic
and explainable so tests and local dev need no external service.
"""

from __future__ import annotations

from decimal import Decimal

import requests
from django.conf import settings

_DECIMAL_2 = Decimal("0.01")


class InsuranceProvider:
    """Contract every insurance provider must fulfil."""

    def quote(self, product, user, room=None) -> dict:
        raise NotImplementedError


class RuleBasedInsuranceProvider(InsuranceProvider):
    """Deterministic quoting from product price + trust/room signals."""

    def quote(self, product, user, room=None) -> dict:
        base = Decimal(str(product.price_monthly))
        price = base
        reasons: list[str] = []

        # Room value: higher-rent rooms carry higher risk-adjusted premium.
        if room is not None and room.price:
            ratio = Decimal(str(room.price)) / Decimal("15000")
            ratio = min(Decimal("1.0"), max(Decimal("0.8"), ratio))
            price = price * ratio
            reasons.append(f"room value factor {ratio}")

        # Trusted tenants earn a small discount.
        if getattr(user, "tenant_verified", False):
            price = price * Decimal("0.95")
            reasons.append("verified tenant -5%")
        elif getattr(user, "nid_verified", False):
            price = price * Decimal("0.97")
            reasons.append("NID-verified -3%")

        price = price.quantize(_DECIMAL_2)
        return {
            "price": price,
            "base_price": base,
            "reasons": reasons,
            "provider": "rule",
        }


class HttpGatewayInsuranceProvider(InsuranceProvider):
    """Optional HTTP gateway; falls back to the rule-based quote on any
    failure so a partner outage never blocks quoting."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def quote(self, product, user, room=None) -> dict:
        try:
            response = requests.post(
                self.endpoint,
                json={
                    "product_code": product.code,
                    "user_id": user.pk,
                    "room_id": room.pk if room else None,
                },
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            return {
                "price": Decimal(str(data["price"])).quantize(_DECIMAL_2),
                "reasons": data.get("reasons", []),
                "provider": "http",
            }
        except Exception:
            return RuleBasedInsuranceProvider().quote(product, user, room)


def get_insurance_provider() -> InsuranceProvider:
    if getattr(settings, "INSURANCE_PROVIDER", "rule") == "http" and settings.INSURANCE_GATEWAY_URL:
        return HttpGatewayInsuranceProvider(settings.INSURANCE_GATEWAY_URL)
    return RuleBasedInsuranceProvider()
