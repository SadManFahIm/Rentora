"""AI Negotiation Agent domain services — Phase 19.4.

Everything the tools/views depend on lives here. The golden rules enforced
server-side:

* **Participants only** — every read/write resolves the negotiation from a
  ``negotiation_key`` and verifies the acting user is tenant or landlord.
* **No autonomous finalization** — ``negotiation.accept`` and
  ``negotiation.finalize`` never run on their own; they only execute through
  the SDK's exactly-once ``apply_proposal`` path after the participant
  approved. The executor re-verifies ownership/state inside the same locked
  block (defense in depth against replay/stale application).
* **Write ≠ send** — ``create_offer`` / ``counter_offer`` produce a DRAFT
  offer; only ``message.send`` (its own explicit approval) posts it into the
  real tenant↔landlord chat thread.
* **Stale protection + expiry** — terminal/expired negotiations reject new
  writes; sent offers expire after ``offer_ttl_days``; every executor is
  idempotent (re-applying a done result is a no-op).
* **Grounding** — context/history only ever surface stored rows (room fields,
  market insight, PI badge, real chat messages, the acting party's own
  boundaries). Never the counterparty's private constraints.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from . import constants as C
from . import models as M


class NegotiationError(Exception):
    """Base for Phase 19.4 errors (mapped to bounded API/executor failures)."""


class NegotiationConsentError(NegotiationError):
    """A participant self-consent could not be completed."""


class NegotiationNotFound(NegotiationError):
    """The referenced negotiation/offer does not exist or isn't the user's."""


# ---------------------------------------------------------------------------
# Lookup / ownership
# ---------------------------------------------------------------------------


def _parse_key(value: Any, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise NegotiationError(f"invalid_{label}") from None


def resolve_negotiation(negotiation_key: Any, user) -> M.Negotiation:
    """Load one negotiation by key for a participant (or raise)."""
    key = _parse_key(negotiation_key, "negotiation_key")
    negotiation = (
        M.Negotiation.objects.select_related("room", "tenant", "landlord", "chat_room")
        .filter(negotiation_key=key)
        .first()
    )
    if negotiation is None:
        raise NegotiationNotFound("negotiation_not_found")
    if M.Negotiation.role_of(negotiation, user) == "":
        if getattr(user, "is_staff", False) or getattr(user, "role", "") == "admin":
            return negotiation  # staff visibility for review/audit
        raise NegotiationNotFound("negotiation_not_found")
    return negotiation


def resolve_own_offer(negotiation: M.Negotiation, offer_key: Any) -> M.NegotiationOffer:
    key = _parse_key(offer_key, "offer_key")
    offer = (
        M.NegotiationOffer.objects.select_related("sender")
        .filter(offer_key=key, negotiation=negotiation)
        .first()
    )
    if offer is None:
        raise NegotiationNotFound("offer_not_found")
    return offer


def participant_role(negotiation: M.Negotiation, user) -> str:
    return M.Negotiation.role_of(negotiation, user)


# ---------------------------------------------------------------------------
# Creation + constraints
# ---------------------------------------------------------------------------


def get_or_create_negotiation(
    *, room, tenant, landlord, conversation=None
) -> tuple[M.Negotiation, bool]:
    """Get the unique negotiation for (room, tenant, landlord), or create it.

    The unique constraint makes concurrent creation safe: the create is retried
    as a lookup when a race loses. New negotiations start INITIATED with a TTL.
    """
    from agents.models import AgentConversation

    lock_role = "tenant" if tenant.pk == landlord.pk else ""
    defaults = {
        "expires_at": timezone.now()
        + timezone.timedelta(days=C.NegotiationSettings().negotiation_ttl_days),
    }
    negotiation, created = M.Negotiation.objects.get_or_create(
        room=room, tenant=tenant, landlord=landlord, defaults=defaults
    )
    if created:
        M.record_event(negotiation, "created", actor=tenant)
    if conversation is not None and isinstance(conversation, AgentConversation):
        owner = conversation.user
        if owner is not None:
            owner_pk = getattr(owner, "pk", None)
            if negotiation.tenant_id == owner_pk and negotiation.tenant_conversation_id is None:
                negotiation.tenant_conversation = conversation
                negotiation.save(update_fields=["tenant_conversation"])
            elif (
                negotiation.landlord_id == owner_pk and negotiation.landlord_conversation_id is None
            ):
                negotiation.landlord_conversation = conversation
                negotiation.save(update_fields=["landlord_conversation"])
    if lock_role:
        pass  # guard against self-negotiation handled by the caller before here
    return negotiation, created


def bind_conversation(negotiation: M.Negotiation, conversation, user) -> bool:
    """Attach one party's agent chat to the negotiation (first one wins)."""
    from agents.models import AgentConversation

    if not isinstance(conversation, AgentConversation):
        return False
    owner_pk = getattr(conversation.user, "pk", None)
    if owner_pk is None:
        return False
    if negotiation.tenant_id == owner_pk and negotiation.tenant_conversation_id is None:
        negotiation.tenant_conversation = conversation
        negotiation.save(update_fields=["tenant_conversation"])
        return True
    if negotiation.landlord_id == owner_pk and negotiation.landlord_conversation_id is None:
        negotiation.landlord_conversation = conversation
        negotiation.save(update_fields=["landlord_conversation"])
        return True
    return False


_VALID_BOUNDS = frozenset(
    {"max_budget", "min_rent", "deposit_max", "deposit_min", "move_in_date", "other_notes"}
)


def _sanitize_constraints(constraints: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(constraints, dict):
        raise NegotiationError("invalid_boundaries")
    out: dict[str, Any] = {}
    num_keys = {"max_budget", "min_rent", "deposit_max", "deposit_min"}
    for key, value in constraints.items():
        if key not in _VALID_BOUNDS:
            continue
        if key in num_keys:
            try:
                number = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                continue
            out[key] = str(max(Decimal("0"), number))
        elif key == "move_in_date":
            out[key] = str(value)[:10]
        elif key == "other_notes":
            out[key] = str(value).strip()[:500]
    return out


def set_constraints(negotiation: M.Negotiation, user, constraints) -> dict[str, Any]:
    """Record the acting participant's own explicit boundaries (private)."""
    role = M.Negotiation.role_of(negotiation, user)
    if role == "":
        raise NegotiationNotFound("negotiation_not_found")
    clean = _sanitize_constraints(constraints)
    if role == "tenant":
        negotiation.tenant_constraints = clean
    else:
        negotiation.landlord_constraints = clean
    negotiation.save(update_fields=[f"{role}_constraints", "updated_at"])
    M.record_event(negotiation, "boundary_set", actor=user, **clean)
    return clean


# ---------------------------------------------------------------------------
# Offers — draft → send (each step is its own explicit consent)
# ---------------------------------------------------------------------------


def draft_offer(
    negotiation: M.Negotiation,
    user,
    *,
    amount: Any,
    kind: str = "offer",
    message: str = "",
    move_in_date: str = "",
    deposit_bdt: Any = None,
    default_message: bool = True,
) -> dict[str, Any]:
    """Create (or re-fetch) a DRAFT offer for the acting party.

    Applies only via ``apply_proposal`` for ``negotiation.create_offer`` /
    ``negotiation.counter_offer``. Replay-safe: a matching DRAFT for the same
    sender+kind+amount returns that row (``already_drafted``) instead of
    creating another.
    """
    cfg = C.NegotiationSettings()
    role = M.Negotiation.role_of(negotiation, user)
    if role == "":
        raise NegotiationNotFound("negotiation_not_found")
    if not cfg.enabled:
        raise NegotiationError("feature_disabled")
    if negotiation.is_terminal:
        raise NegotiationError("negotiation_stale")

    try:
        amount_dec = Decimal(str(amount)).quantize(Decimal("1"))
    except (InvalidOperation, TypeError, ValueError):
        raise NegotiationError("invalid_amount") from None
    if amount_dec < cfg.min_amount or amount_dec > cfg.max_amount:
        raise NegotiationError("amount_out_of_bounds")
    if kind not in ("offer", "counter"):
        raise NegotiationError("invalid_kind")

    open_count = negotiation.offers.filter(
        status__in=[M.OfferStatus.DRAFT, M.OfferStatus.SENT], sender=user
    ).count()
    if open_count >= cfg.max_open_offers:
        raise NegotiationError("too_many_open_offers")

    existing = (
        negotiation.offers.filter(
            sender=user, kind=kind, amount=amount_dec, status=M.OfferStatus.DRAFT
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return dict(
            ok="offer_drafted",
            offer_key=str(existing.offer_key),
            amount=str(amount_dec),
            kind=existing.kind,
            status=existing.status,
            already_drafted=True,
        )

    meta: dict[str, Any] = {}
    if move_in_date:
        meta["move_in_date"] = str(move_in_date)[:10]
    if deposit_bdt not in (None, ""):
        from contextlib import suppress

        with suppress(InvalidOperation, TypeError, ValueError):
            meta["deposit_bdt"] = str(Decimal(str(deposit_bdt)).quantize(Decimal("1")))
    with transaction.atomic():
        offer = M.NegotiationOffer.objects.create(
            negotiation=negotiation,
            sender=user,
            kind=kind,
            amount=amount_dec,
            message=(message or "").strip()[: cfg.max_message_len],
            meta=meta,
            status=M.OfferStatus.DRAFT,
        )
        M.record_event(
            negotiation,
            "offer_drafted",
            actor=user,
            offer_key=str(offer.offer_key),
            kind=offer.kind,
            amount=str(offer.amount),
        )
    return dict(
        ok="offer_drafted",
        offer_key=str(offer.offer_key),
        amount=str(offer.amount),
        kind=offer.kind,
        status=offer.status,
        already_drafted=False,
    )


def _get_or_create_chat_room(negotiation: M.Negotiation) -> Any:
    """Return the tenant↔landlord DIRECT chat room for the listing."""
    from chat.models import ChatRoom, ChatRoomMembership

    if negotiation.chat_room_id is not None:
        return negotiation.chat_room
    existing = (
        ChatRoom.objects.filter(room_type=ChatRoom.RoomType.DIRECT, listing=negotiation.room)
        .filter(members=negotiation.tenant)
        .filter(members=negotiation.landlord)
        .first()
    )
    if existing is not None:
        negotiation.chat_room = existing
        negotiation.save(update_fields=["chat_room"])
        return existing
    room = ChatRoom.objects.create(room_type=ChatRoom.RoomType.DIRECT, listing=negotiation.room)
    ChatRoomMembership.objects.bulk_create(
        [
            ChatRoomMembership(chat_room=room, user=negotiation.tenant),
            ChatRoomMembership(chat_room=room, user=negotiation.landlord),
        ]
    )
    negotiation.chat_room = room
    negotiation.save(update_fields=["chat_room"])
    return room


@transaction.atomic
def send_offer(
    negotiation: M.Negotiation,
    user,
    offer: M.NegotiationOffer,
    *,
    actor=None,
    message: str = "",
) -> dict[str, Any]:
    """Post a DRAFT offer into the real tenant↔landlord chat thread.

    Only ``message.send`` reaches here, after its own explicit approval; the
    locked block re-marks everything idempotently so replay/stale application
    can never double-send.
    """
    cfg = C.NegotiationSettings()
    if not cfg.enabled:
        raise NegotiationError("feature_disabled")
    locked_offer = (
        M.NegotiationOffer.objects.select_for_update()
        .select_related("negotiation")
        .get(pk=offer.pk)
    )
    negotiation = locked_offer.negotiation
    if (
        getattr(user, "pk", None) != locked_offer.sender_id
        and getattr(actor, "pk", None) != locked_offer.sender_id
    ):
        raise PermissionDenied("not_offer_sender")
    if negotiation.is_terminal:
        raise NegotiationError("negotiation_stale")
    if negotiation.expires_at is not None and timezone.now() >= negotiation.expires_at:
        raise NegotiationError("negotiation_expired")
    if locked_offer.is_expired:
        raise NegotiationError("offer_expired")

    # Replay-safe: already sent is a no-op success (not an error).
    if locked_offer.status == M.OfferStatus.SENT:
        return _sent_payload(locked_offer, already_sent=True)
    if locked_offer.status != M.OfferStatus.DRAFT:
        raise NegotiationError(f"cannot_send_{locked_offer.status}")

    from chat.models import Message
    from chat.utils import is_blocked_between

    if is_blocked_between(negotiation.tenant, negotiation.landlord):
        raise NegotiationError("participants_blocked")

    body = (message or locked_offer.message or "").strip()
    if not body:
        room_model = negotiation.room
        listed = f"৳{int(room_model.price):,}" if room_model.price else "৳—"
        body = (
            f"{'Counter offer' if locked_offer.kind == 'counter' else 'Offer'}: "
            f"৳{int(locked_offer.amount):,}/month (listed {listed})."
        )
    body = body[: cfg.max_message_len]

    chat_room = _get_or_create_chat_room(negotiation)
    chat_msg = Message.objects.create(
        chat_room=chat_room,
        sender=locked_offer.sender,
        content=body,
        message_type=Message.MessageType.TEXT,
    )

    locked_offer.status = M.OfferStatus.SENT
    locked_offer.expires_at = timezone.now() + timezone.timedelta(days=cfg.offer_ttl_days)
    locked_offer.chat_message = chat_msg
    locked_offer.save(update_fields=["status", "expires_at", "chat_message", "updated_at"])

    target = M.NegotiationStatus.OFFER_PENDING
    if locked_offer.kind == "counter":
        target = M.NegotiationStatus.COUNTER_OFFER_PENDING
    M.transition_negotiation(
        negotiation,
        target,
        actor=locked_offer.sender,
        event="counter_sent" if locked_offer.kind == "counter" else "offer_sent",
        offer_key=str(locked_offer.offer_key),
        amount=str(locked_offer.amount),
    )

    from .notifications import notify_offer_sent

    notify_offer_sent(negotiation, locked_offer)
    return _sent_payload(locked_offer, already_sent=False)


def _sent_payload(offer: M.NegotiationOffer, *, already_sent: bool) -> dict[str, Any]:
    return dict(
        ok="offer_sent",
        offer_key=str(offer.offer_key),
        amount=str(offer.amount),
        kind=offer.kind,
        status=offer.status,
        expires_at=offer.expires_at.isoformat() if offer.expires_at else None,
        chat_message_id=offer.chat_message_id,
        already_sent=already_sent,
    )


@transaction.atomic
def reject_offer(
    negotiation: M.Negotiation, user, offer: M.NegotiationOffer, *, reason=""
) -> dict[str, Any]:
    """Counterparty rejects an outstanding offer; the sender withdraws it.

    Plain-user action (no SDK proposal): it only marks an offer terminal and
    never changes monetary intent. If no SENT offer remains, the negotiation
    falls back to ACTIVE so both sides can still negotiate.
    """
    locked = M.NegotiationOffer.objects.select_for_update().get(pk=offer.pk)
    if locked.status not in (M.OfferStatus.SENT,):
        if locked.status == M.OfferStatus.DRAFT and locked.sender_id == getattr(user, "pk", None):
            raise NegotiationError("draft_not_sent")
        raise NegotiationError(f"cannot_reject_{locked.status}")
    if negotiation.is_terminal or (
        negotiation.expires_at and timezone.now() >= negotiation.expires_at
    ):
        raise NegotiationError("negotiation_stale")

    sender = locked.sender_id == getattr(user, "pk", None)
    counterpart = (
        negotiation.tenant_id == getattr(user, "pk", None)
        or negotiation.landlord_id == getattr(user, "pk", None)
    ) and not sender
    if not sender and not counterpart:
        raise PermissionDenied("not_participant")

    if sender:
        locked.status = M.OfferStatus.WITHDRAWN
        event = "offer_withdrawn"
        action_note = ("withdrawn", reason)
    else:
        locked.status = M.OfferStatus.REJECTED
        event = "offer_rejected"
        action_note = ("rejected", reason)
    locked.meta = {**locked.meta, **({"reject_reason": (reason or "")[:500]} if reason else {})}
    locked.save(update_fields=["status", "meta", "updated_at"])
    M.record_event(
        negotiation, event, actor=user, offer_key=str(locked.offer_key), amount=str(locked.amount)
    )

    if not negotiation.offers.filter(status=M.OfferStatus.SENT).exists():
        M.transition_negotiation(negotiation, M.NegotiationStatus.ACTIVE, actor=user)

    return dict(ok=f"offer_{action_note[0]}", offer_key=str(locked.offer_key), status=locked.status)


@transaction.atomic
def accept_offer(
    negotiation: M.Negotiation,
    user,
    offer: M.NegotiationOffer,
    *,
    actor=None,
    note: str = "",
) -> dict[str, Any]:
    """Mark an outstanding offer accepted (HIGH_RISK, participant consent only).

    Neither this step nor ``finalize`` creates a booking/payment/deposit — the
    contract hand-off is a notification with a road to the booking flow. An
    already-accepted offer / negotiation is a replay-safe no-op.
    """
    cfg = C.NegotiationSettings()
    if not cfg.enabled:
        raise NegotiationError("feature_disabled")
    if M.Negotiation.role_of(negotiation, user) == "":
        raise PermissionDenied("not_participant")
    if M.Negotiation.role_of(negotiation, actor) == "" and getattr(actor, "pk", None):
        raise PermissionDenied("not_participant")

    locked = M.NegotiationOffer.objects.select_for_update().get(pk=offer.pk)
    if locked.negotiation_id != negotiation.pk:
        raise NegotiationError("offer_mismatch")
    if negotiation.is_terminal:
        raise NegotiationError("negotiation_stale")
    if locked.sender_id == getattr(user, "pk", None):
        # A party never "accepts" their own offer — only the counterparty may.
        raise NegotiationError("cannot_accept_own_offer")
    if locked.status == M.OfferStatus.ACCEPTED:
        return dict(
            ok="offer_accepted",
            offer_key=str(locked.offer_key),
            status=locked.status,
            already_accepted=True,
        )
    if locked.status != M.OfferStatus.SENT:
        raise NegotiationError(f"cannot_accept_{locked.status}")
    if locked.is_expired:
        raise NegotiationError("offer_expired")

    locked.status = M.OfferStatus.ACCEPTED
    locked.meta = {**locked.meta, **({"accept_note": (note or "")[:500]} if note else {})}
    locked.save(update_fields=["status", "meta", "updated_at"])

    accepting_party = negotiation.counterparty(locked.sender)
    M.transition_negotiation(
        negotiation,
        M.NegotiationStatus.ACCEPTED,
        actor=locked.sender,
        event="offer_accepted",
        offer_key=str(locked.offer_key),
        amount=str(locked.amount),
        accepted_by=accepting_party.id if accepting_party is not None else "",
    )
    from .notifications import notify_negotiation_accepted

    notify_negotiation_accepted(negotiation, locked)
    return dict(
        ok="negotiation_accepted", offer_key=str(locked.offer_key), status=negotiation.status
    )


@transaction.atomic
def finalize_negotiation(
    negotiation: M.Negotiation,
    user,
    *,
    actor=None,
    offer: M.NegotiationOffer | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Close an ACCEPTED negotiation and hand off to the booking flow.

    Beware the golden rule: this never books, never charges, never edits the
    room. Participants get a notification with an action route. A CLOSED
    negotiation is an idempotent no-op.
    """
    cfg = C.NegotiationSettings()
    if not cfg.enabled:
        raise NegotiationError("feature_disabled")
    if M.Negotiation.role_of(negotiation, user) == "":
        raise PermissionDenied("not_participant")
    if negotiation.status == M.NegotiationStatus.CLOSED:
        return dict(ok="negotiation_closed", status=negotiation.status, already_closed=True)
    if negotiation.status != M.NegotiationStatus.ACCEPTED:
        raise NegotiationError("negotiation_not_accepted")
    if offer is not None and offer.status != M.OfferStatus.ACCEPTED:
        raise NegotiationError("offer_not_accepted")

    M.transition_negotiation(
        negotiation,
        M.NegotiationStatus.CLOSED,
        actor=user,
        event="negotiation_closed",
        note=(note or "")[:500],
    )
    from .notifications import notify_negotiation_closed

    notify_negotiation_closed(negotiation)
    return dict(ok="negotiation_closed", status=negotiation.status)


@transaction.atomic
def reject_negotiation(negotiation: M.Negotiation, user, *, reason="") -> dict[str, Any]:
    """A participant rejects the whole negotiation (terminal REJECTED)."""
    if M.Negotiation.role_of(negotiation, user) == "":
        raise PermissionDenied("not_participant")
    if negotiation.is_terminal:
        raise NegotiationError("negotiation_already_terminal")
    M.transition_negotiation(
        negotiation,
        M.NegotiationStatus.REJECTED,
        actor=user,
        event="negotiation_rejected",
        reason=(reason or "")[:500],
    )
    from .notifications import notify_negotiation_ended

    notify_negotiation_ended(negotiation, "rejected")
    return dict(ok="negotiation_rejected", status=negotiation.status)


@transaction.atomic
def cancel_negotiation(negotiation: M.Negotiation, user, *, reason="") -> dict[str, Any]:
    """A participant cancels the whole negotiation (terminal CANCELLED)."""
    if M.Negotiation.role_of(negotiation, user) == "":
        raise PermissionDenied("not_participant")
    if negotiation.is_terminal:
        raise NegotiationError("negotiation_already_terminal")
    M.transition_negotiation(
        negotiation,
        M.NegotiationStatus.CANCELLED,
        actor=user,
        event="negotiation_cancelled",
        reason=(reason or "")[:500],
    )
    from .notifications import notify_negotiation_ended

    notify_negotiation_ended(negotiation, "cancelled")
    return dict(ok="negotiation_cancelled", status=negotiation.status)


@transaction.atomic
def expire_negotiations(*, dry_run: bool = False) -> dict[str, int]:
    """Hourly/daily cleanup: expire SENT offers and stale open negotiations."""
    now = timezone.now()
    offers = M.NegotiationOffer.objects.filter(
        status=M.OfferStatus.SENT, expires_at__lte=now
    ).select_related("negotiation", "sender")
    open_negotiations = M.Negotiation.objects.filter(status__in=M.OPEN_STATES, expires_at__lte=now)
    if dry_run:
        return {
            "offers_expired": offers.count(),
            "negotiations_expired": open_negotiations.count(),
        }

    offers_expired = 0
    for offer in offers.select_for_update():
        offer.status = M.OfferStatus.EXPIRED
        offer.save(update_fields=["status", "updated_at"])
        M.record_event(
            offer.negotiation,
            "offer_expired",
            offer_key=str(offer.offer_key),
            amount=str(offer.amount),
        )
        offers_expired += 1
        from .notifications import notify_offer_expired

        notify_offer_expired(offer.negotiation, offer)

    negotiations_expired = 0
    for negotiation in open_negotiations.select_for_update():
        M.transition_negotiation(
            negotiation,
            M.NegotiationStatus.EXPIRED,
            event="negotiation_expired",
        )
        negotiations_expired += 1
        from .notifications import notify_negotiation_ended

        notify_negotiation_ended(negotiation, "expired")

    return {
        "offers_expired": offers_expired,
        "negotiations_expired": negotiations_expired,
    }


# ---------------------------------------------------------------------------
# Consent (participant self-approval) — mirrors the 19.2/19.3 pattern
# ---------------------------------------------------------------------------


def _owner_of(proposal) -> Any:
    run = proposal.run
    if run is None or run.conversation is None:
        raise NegotiationConsentError("no_owner_conversation")
    owner = run.conversation.user
    if owner is None:
        raise NegotiationConsentError("no_owner_conversation")
    return owner


@transaction.atomic
def self_consent_approve(user, proposal) -> Any:
    """Approve + apply one of the negotiation tools as its conversation owner.

    Idempotent + replay-safe through ``agents.services.apply_proposal`` (the
    same exactly-once path staff reviewers use). The executors re-verify
    participant ownership and negotiation room/state inside the locked apply.
    """
    from agents.models import AgentProposal
    from agents.services import apply_proposal

    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        return locked
    if locked.status != "pending":
        raise NegotiationConsentError(f"cannot_consent_{locked.status}")
    owner = _owner_of(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")

    tool_name = (locked.action or {}).get("tool", "")
    if tool_name not in C.NEGOTIATION_TOOLS:
        raise NegotiationConsentError("unsupported_proposal_type")
    if locked.is_expired:
        raise NegotiationConsentError("expired")

    # The acting party must actually be a participant of the referenced
    # negotiation (belt-and-braces before anything is approved).
    arguments = (locked.action or {}).get("arguments") or {}
    if arguments.get("negotiation_key"):
        try:
            negotiation = resolve_negotiation(arguments["negotiation_key"], user)
        except NegotiationError as exc:
            raise NegotiationConsentError(str(exc)) from exc
        if M.Negotiation.role_of(negotiation, user) == "":
            raise NegotiationConsentError("not_participant")

    locked.status = "approved"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.meta = {
        **locked.meta,
        "consent": "negotiation_self_consent",
        "approval_note": "approved by the conversation owner (negotiation consent)",
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=user,
            action="agent.proposal.self_consented",
            target=locked,
            detail=f"negotiation self-consent for proposal {locked.proposal_key}",
        )
    except Exception:
        pass
    return apply_proposal(locked, actor=user)


@transaction.atomic
def self_reject(user, proposal, *, reason: str = ""):
    """Reject a pending negotiation proposal as its conversation owner."""
    from agents.models import AgentProposal

    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        raise NegotiationConsentError("cannot_reject_applied")
    if locked.status != "pending":
        raise NegotiationConsentError(f"cannot_reject_{locked.status}")
    owner = _owner_of(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")
    if (locked.action or {}).get("tool", "") not in C.NEGOTIATION_TOOLS:
        raise NegotiationConsentError("unsupported_proposal_type")
    if locked.is_expired:
        raise NegotiationConsentError("expired")

    locked.status = "rejected"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.rejection_reason = (reason or "")[:2000]
    locked.meta = {
        **locked.meta,
        "consent": "negotiation_self_reject",
        "reject_reason": (reason or "")[:500],
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=user,
            action="agent.proposal.self_rejected",
            target=locked,
            detail=f"negotiation rejected proposal {locked.proposal_key}",
        )
    except Exception:
        pass
    return locked


# ---------------------------------------------------------------------------
# Grounded conversation/context payloads
# ---------------------------------------------------------------------------


def _public_room(negotiation: M.Negotiation) -> dict[str, Any]:
    try:
        from rental_agent.services import room_card

        return room_card(negotiation.room)
    except Exception:
        return {"id": negotiation.room_id}


def _public_insights(negotiation: M.Negotiation) -> dict[str, Any]:
    try:
        from rental_agent.services import room_insights

        return room_insights(negotiation.room)
    except Exception:
        return {}


def _recent_chat_messages(negotiation: M.Negotiation, user, limit: int) -> list[dict[str, Any]]:
    """Sanitized tail of the real peer thread the acting party can see."""
    if negotiation.chat_room_id is None:
        return []
    from chat.models import Message

    rows = (
        Message.objects.filter(chat_room_id=negotiation.chat_room_id)
        .exclude(is_deleted=True)
        .order_by("-created_at")[:limit]
    )
    out = []
    for row in reversed(list(rows)):
        sender_role = ""
        if row.sender_id == negotiation.tenant_id:
            sender_role = "tenant"
        elif row.sender_id == negotiation.landlord_id:
            sender_role = "landlord"
        out.append(
            {
                "sender": sender_role,
                "sender_name": getattr(row.sender, "get_full_name", lambda: "")()
                or getattr(row.sender, "username", ""),
                "content": (row.content or "")[:2000],
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def _offer_payload(offer: M.NegotiationOffer, role: str) -> dict[str, Any]:
    sender_role = "tenant" if offer.sender_id == offer.negotiation.tenant_id else "landlord"
    return {
        "key": str(offer.offer_key),
        "kind": offer.kind,
        "amount": int(offer.amount),
        "message": offer.message,
        "meta": dict(offer.meta or {}),
        "status": offer.status,
        "sender_role": sender_role,
        "sender_name": getattr(offer.sender, "get_full_name", lambda: "")()
        or getattr(offer.sender, "username", ""),
        "created_at": offer.created_at.isoformat() if offer.created_at else None,
        "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
        "can_accept": offer.status == "sent" and sender_role != role and offer.negotiation.is_open,
        "can_reject": offer.status == "sent" and sender_role != role and offer.negotiation.is_open,
        "can_withdraw": offer.status == "sent" and sender_role == role,
    }


def negotiation_payload(negotiation: M.Negotiation, user=None) -> dict[str, Any]:
    """Enriched JSON for the API + UI (no side effects, no counterparty's
    private constraints)."""
    role = M.Negotiation.role_of(negotiation, user) if user is not None else ""
    peer = negotiation.counterparty(user) if user is not None else negotiation.landlord

    feature_enabled = False
    try:
        from ai_intelligence.services import is_feature_available

        feature_enabled = is_feature_available(C.FEATURE_ID, user=user)
    except Exception:
        feature_enabled = False

    offers = []
    if negotiation.pk:
        offers = [
            _offer_payload(o, role)
            for o in negotiation.offers.select_related("sender", "negotiation").order_by(
                "-created_at"
            )
        ]

    events = []
    if negotiation.pk:
        events = list(negotiation.events.select_related("actor").order_by("-created_at")[:30])

    return {
        "key": str(negotiation.negotiation_key),
        "room_id": negotiation.room_id,
        "room": _public_room(negotiation),
        "insights": _public_insights(negotiation),
        "status": negotiation.status,
        "status_label": dict(M.NegotiationStatus.choices).get(
            negotiation.status, negotiation.status
        ),
        "my_role": role,
        "tenant": {
            "name": getattr(negotiation.tenant, "get_full_name", lambda: "")()
            or getattr(negotiation.tenant, "username", ""),
        },
        "landlord": {
            "name": getattr(negotiation.landlord, "get_full_name", lambda: "")()
            or getattr(negotiation.landlord, "username", ""),
            "is_owner": negotiation.landlord_id == getattr(negotiation.room.owner, "pk", None),
        },
        "peer_name": (getattr(peer, "get_full_name", lambda: "")() or getattr(peer, "username", ""))
        if peer is not None
        else "",
        "my_constraints": (negotiation.party_constraints(user) if user is not None else {}),
        "peer_constraints_set": bool(
            negotiation.landlord_constraints if role == "tenant" else negotiation.tenant_constraints
        ),
        "offers": offers,
        "timeline": [
            {
                "event": e.event_type,
                "actor_name": getattr(e.actor, "username", "") or "",
                "detail": dict(e.detail or {}),
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "expires_at": negotiation.expires_at.isoformat() if negotiation.expires_at else None,
        "is_open": negotiation.is_open,
        "features": {"negotiation_agent_enabled": feature_enabled},
        "chat_room_id": negotiation.chat_room_id,
        "can_reject": role != ""
        and negotiation.is_open
        and negotiation.status not in ("rejected",),
        "can_cancel": role != "" and negotiation.is_open,
    }
