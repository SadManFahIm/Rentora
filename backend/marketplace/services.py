"""Marketplace services: order confirmation (commissions + ledger) and
cross-sell recommendations."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from monetization.services.commissions import commission_rate, create_commission
from monetization.services.ledger import record_entry
from notifications.models import Notification
from notifications.utils import create_notification

from .models import AddonOrder, AddonProvider, AddonService


class MarketplaceError(Exception):
    """Domain error (bad state transition, invalid order)."""


# Deterministic cross-sell priority: insurance first for a fresh lease, then
# practical move-in services. This is a rule-based recommendation — explainable.
_RECOMMENDATION_PRIORITY = {
    AddonService.Category.INSURANCE: 0,
    AddonService.Category.CLEANING: 1,
    AddonService.Category.RELOCATION: 2,
    AddonService.Category.UTILITIES: 3,
    AddonService.Category.FURNITURE: 4,
    AddonService.Category.REPAIRS: 5,
}


def recommend_addons(booking, limit: int = 4):
    """Top add-on services to cross-sell for a freshly-booked room.

    Deterministic: priority by category fit for a new lease, then rating.
    Returns the selected ``AddonService`` queryset results.
    """
    services = list(
        AddonService.objects.filter(
            is_active=True, provider__status=AddonProvider.Status.ACTIVE
        ).select_related("provider")
    )
    services.sort(key=lambda s: (_RECOMMENDATION_PRIORITY.get(s.category, 9), -(s.rating_avg or 0)))
    return services[:limit]


def confirm_order(order: AddonOrder, actor) -> AddonOrder:
    """Confirm an order and (once) settle provider + broker commissions.

    Idempotent: only a PENDING order can be confirmed, and the commission /
    ledger idempotency keys are the order id, so retries never double-pay.
    """
    with transaction.atomic():
        order = AddonOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != AddonOrder.Status.PENDING:
            raise MarketplaceError(f"Cannot confirm a {order.status} order.")
        order.status = AddonOrder.Status.CONFIRMED
        order.save(update_fields=["status", "updated_at"])

        provider = order.service.provider
        provider_rate = (
            provider.commission_rate
            if provider.commission_rate is not None
            else commission_rate("marketplace")
        )
        provider_share = (order.total * Decimal(str(provider_rate)) / Decimal(100)).quantize(
            Decimal("0.01")
        )

        broker_share = Decimal("0.00")
        broker = order.broker
        if broker is not None and broker.is_verified():
            broker_rate = commission_rate("broker")
            broker_share = (order.total * broker_rate / Decimal(100)).quantize(Decimal("0.01"))
            broker_commission = create_commission(
                kind="marketplace_order",
                recipient=broker.user,
                gross_amount=order.total,
                scope="broker",
                source=order,
                idempotency_key=f"marketplace-broker-{order.pk}",
                detail={"order_id": order.pk, "service": order.service.title},
            )
            if broker_commission.status == "pending":
                create_notification(
                    user=broker.user,
                    notification_type=Notification.Type.COMMISSION_EARNED,
                    title="Commission earned",
                    message=f"You earned a {broker_commission.amount} BDT referral commission.",
                    action_url="/dashboard?tab=broker",
                )

        create_commission(
            kind="marketplace_order",
            recipient=provider.user,
            gross_amount=order.total,
            scope="marketplace",
            source=order,
            idempotency_key=f"marketplace-provider-{order.pk}",
            rate_override=provider_rate,
            detail={"order_id": order.pk, "service": order.service.title},
        )

        platform_amount = order.total - provider_share - broker_share
        record_entry(
            entry_type="addon_sale",
            scope="marketplace",
            user=order.tenant,
            gross=order.total,
            platform_amount=platform_amount,
            partner_amount=provider_share + broker_share,
            source=order,
            idempotency_key=f"marketplace-sale-{order.pk}",
            detail={
                "provider_share": str(provider_share),
                "broker_share": str(broker_share),
                "provider_rate": str(provider_rate),
            },
        )

        create_notification(
            user=provider.user,
            notification_type=Notification.Type.ADDON_ORDER_CONFIRMED,
            title="New order confirmed",
            message=f"'{order.service.title}' was confirmed for {order.total} BDT.",
            action_url="/dashboard?tab=marketplace",
        )
    return order
