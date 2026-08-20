"""Commission engine — idempotent commission creation for all partner scopes."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction

from ..models import Commission, CommissionRule

_DECIMAL_2 = Decimal("0.01")


def default_rate(scope: str) -> Decimal:
    return Decimal(str(getattr(settings, "COMMISSION_DEFAULT_RATES", {}).get(scope, 0)))


def commission_rate(scope: str, override: Decimal | None = None) -> Decimal:
    """The rate for a scope: an explicit override, an active rule, or the
    settings fallback — in that order."""
    if override is not None:
        return Decimal(str(override))
    rule = CommissionRule.objects.filter(scope=scope, active=True).first()
    return rule.rate if rule is not None else default_rate(scope)


def commission_amount(gross_amount: Decimal, rate: Decimal) -> Decimal:
    return (Decimal(str(gross_amount)) * rate / Decimal(100)).quantize(_DECIMAL_2)


def create_commission(
    *,
    kind: str,
    recipient,
    gross_amount: Decimal,
    scope: str,
    source,
    idempotency_key: str,
    rate_override: Decimal | None = None,
    detail: dict | None = None,
) -> Commission:
    """Create a commission exactly once per ``idempotency_key``.

    Replaying the same business event (e.g. a booking approved twice) returns
    the existing commission instead of paying twice.
    """
    existing = Commission.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    rate = commission_rate(scope, rate_override)
    amount = commission_amount(gross_amount, rate)

    with transaction.atomic():
        commission, _ = Commission.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "kind": kind,
                "recipient": recipient,
                "amount": amount,
                "rate": rate,
                "status": Commission.Status.PENDING,
                "source_type": source._meta.label,
                "source_id": str(source.pk),
                "detail": detail or {},
            },
        )
    return commission


def cancel_commission(commission: Commission, *, reason: str = "") -> Commission:
    """Cancel a pending commission (e.g. the booking was reversed)."""
    if commission.status == Commission.Status.PENDING:
        commission.status = Commission.Status.CANCELED
        commission.detail = {**(commission.detail or {}), "cancel_reason": reason}
        commission.save(update_fields=["status", "detail", "updated_at"])
    return commission
