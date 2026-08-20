"""Insurance/credit domain services."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction

from audit.services import log_action
from monetization.services.commissions import commission_rate, create_commission
from monetization.services.ledger import record_entry
from notifications.models import Notification
from notifications.utils import create_notification

from .models import InsuranceQuote
from .providers import get_insurance_provider


class PartnerServiceError(Exception):
    """Domain error (bad quote state, ineligible)."""


def _json_safe(value):
    """Coerce Decimals (and lists/dicts of them) into JSON-storable values."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def create_quote(*, user, product, room=None, broker=None) -> InsuranceQuote:
    """Generate a quote via the configured provider (deterministic default)."""
    provider = get_insurance_provider()
    quote_result = provider.quote(product, user, room)
    quote = InsuranceQuote.objects.create(
        user=user,
        product=product,
        room=room,
        broker=broker,
        price=quote_result["price"],
        quote_data=_json_safe(quote_result),
    )
    return quote


def issue_policy(quote: InsuranceQuote, actor) -> InsuranceQuote:
    """Issue the policy (once): settle broker commission + ledger + notify.

    Idempotent by quote — only a QUOTED quote can be issued.
    """
    with transaction.atomic():
        quote = InsuranceQuote.objects.select_for_update().get(pk=quote.pk)
        if quote.status != InsuranceQuote.Status.QUOTED:
            raise PartnerServiceError(f"Cannot issue a {quote.status} quote.")

        quote.status = InsuranceQuote.Status.ISSUED
        quote.save(update_fields=["status", "updated_at"])

        # Platform revenue = insurance_rate% of the premium; partner keeps the rest.
        ins_rate = commission_rate("insurance")
        platform_share = (quote.price * ins_rate / Decimal(100)).quantize(Decimal("0.01"))

        if quote.broker is not None and quote.broker.is_verified():
            broker_commission = create_commission(
                kind="insurance_policy",
                recipient=quote.broker.user,
                gross_amount=quote.price,
                scope="broker",
                source=quote,
                idempotency_key=f"insurance-broker-{quote.pk}",
                detail={"quote_id": quote.pk, "product": quote.product.code},
            )
            if broker_commission.status == "pending":
                create_notification(
                    user=quote.broker.user,
                    notification_type=Notification.Type.COMMISSION_EARNED,
                    title="Commission earned",
                    message=f"You earned a {broker_commission.amount} BDT insurance commission.",
                    action_url="/dashboard?tab=broker",
                )

        record_entry(
            entry_type="insurance_policy",
            scope="insurance",
            user=quote.user,
            gross=quote.price,
            platform_amount=platform_share,
            partner_amount=quote.price - platform_share,
            source=quote,
            idempotency_key=f"insurance-policy-{quote.pk}",
            detail={"product": quote.product.code, "insurance_rate": str(ins_rate)},
        )

        create_notification(
            user=quote.user,
            notification_type=Notification.Type.INSURANCE_POLICY_ISSUED,
            title="Insurance policy issued",
            message=f"Your {quote.product.name} policy is active at {quote.price} BDT/month.",
            action_url="/services?tab=insurance",
        )
        log_action(actor=actor, action="insurance.policy_issued", target=quote)
    return quote


def check_credit_eligibility(user) -> dict:
    """Deterministic credit eligibility via the configured adapter.

    Rule-based by default: trust verification + rental history translate to
    a pre-approved credit ceiling in BDT. No external call is made unless a
    credit partner/gateway is configured.
    """
    from bookings.models import Booking

    completed = Booking.objects.filter(tenant=user, status=Booking.Status.APPROVED).count()

    score = 300
    reasons: list[str] = []
    if getattr(user, "tenant_verified", False):
        score += 120
        reasons.append("verified tenant")
    if getattr(user, "nid_verified", False):
        score += 60
        reasons.append("NID verified")
    score += min(completed * 20, 120)
    if completed:
        reasons.append(f"{completed} completed bookings")

    eligible = score >= 420
    limit = min(500_000, score * 500) if eligible else 0
    return {
        "eligible": eligible,
        "credit_score": score,
        "preapproved_limit": limit,
        "currency": "BDT",
        "reasons": reasons,
        "provider": getattr(settings, "CREDIT_PROVIDER", "rule"),
    }
