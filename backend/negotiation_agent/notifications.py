"""AI Negotiation Agent notifications (Phase 19.4).

Low volume by design: only materially meaningful moments notify — a new/counter
offer (to the counterparty), acceptance (to both), close with the booking
hand-off (to both), end/expiry, and offer expiry (to its sender). Everything
routes through ``notifications.utils.create_notification`` (the single
sanitized entry point with WebSocket push). Never raises.
"""

from __future__ import annotations

from contextlib import suppress

from . import constants as C

_DASHBOARD_URL = "/dashboard?tab=negotiations"


def notify_offer_sent(negotiation, offer) -> None:
    peer = negotiation.counterparty(offer.sender)
    if peer is None:
        return
    from notifications.utils import create_notification

    kind = "Counter offer" if offer.kind == "counter" else "New offer"
    with suppress(Exception):
        create_notification(
            peer,
            "ai_alert",
            title=f"{kind} in your negotiation",
            message=(
                f"{offer.sender.get_full_name() or offer.sender.username} proposed "
                f"৳{int(offer.amount):,}/month for "
                f"'{negotiation.room.title}' — review and respond when ready."
            ),
            action_url=_DASHBOARD_URL,
            meta={
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
                "feature": C.FEATURE_ID,
            },
        )


def notify_offer_expired(negotiation, offer) -> None:
    from notifications.utils import create_notification

    with suppress(Exception):
        create_notification(
            offer.sender,
            "ai_alert",
            title="Your negotiation offer expired",
            message=(
                f"The ৳{int(offer.amount):,}/month offer for "
                f"'{negotiation.room.title}' expired without a response."
            ),
            action_url=_DASHBOARD_URL,
            meta={"negotiation_key": str(negotiation.negotiation_key), "feature": C.FEATURE_ID},
        )


def notify_negotiation_accepted(negotiation, offer) -> None:
    from notifications.utils import create_notification

    room = negotiation.room
    for party in (negotiation.tenant, negotiation.landlord):
        with suppress(Exception):
            create_notification(
                party,
                "ai_alert",
                title="Negotiation agreed",
                message=(
                    f"You and the other side agreed on ৳{int(offer.amount):,}/month for "
                    f"'{room.title}'. Close the negotiation to move to booking."
                ),
                action_url=_DASHBOARD_URL,
                meta={
                    "negotiation_key": str(negotiation.negotiation_key),
                    "offer_key": str(offer.offer_key),
                    "feature": C.FEATURE_ID,
                },
            )


def notify_negotiation_closed(negotiation) -> None:
    """Close = hand off to the existing booking flow (never books here)."""
    from notifications.utils import create_notification

    room = negotiation.room
    for party in (negotiation.tenant, negotiation.landlord):
        action_url = (
            f"/rooms/{room.pk}/" if party.pk == negotiation.tenant_id else "/dashboard?tab=bookings"
        )
        with suppress(Exception):
            create_notification(
                party,
                "ai_alert",
                title="Negotiation closed — next step",
                message=(
                    f"The negotiation for '{room.title}' is closed. "
                    + (
                        "Open the listing and book while the agreed terms hold."
                        if party.pk == negotiation.tenant_id
                        else "Check your bookings dashboard for the hand-off."
                    )
                ),
                action_url=action_url,
                meta={"negotiation_key": str(negotiation.negotiation_key), "feature": C.FEATURE_ID},
            )


def notify_negotiation_ended(negotiation, reason: str) -> None:
    title = {
        "rejected": "Negotiation rejected",
        "cancelled": "Negotiation cancelled",
        "expired": "Negotiation expired",
    }.get(reason, "Negotiation ended")
    from notifications.utils import create_notification

    room = negotiation.room
    for party in (negotiation.tenant, negotiation.landlord):
        with suppress(Exception):
            create_notification(
                party,
                "ai_alert",
                title=title,
                message=f"The negotiation for '{room.title}' is now {reason}. No terms changed.",
                action_url=_DASHBOARD_URL,
                meta={"negotiation_key": str(negotiation.negotiation_key), "feature": C.FEATURE_ID},
            )
