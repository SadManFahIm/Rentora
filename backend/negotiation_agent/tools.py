"""AI Negotiation Agent SDK tools — Phase 19.4.

Registered through the Phase 19.0 ``AgentToolRegistry``. Tool capabilities:

* **READ_ONLY**
  - ``negotiation.context`` — the grounded, participant-authorized snapshot
    (listing card, price insight, PI badge, offers, the acting party's own
    boundaries, real peer chat messages). Never the counterparty's private
    constraints.
  - ``negotiation.history`` — the auditable event timeline.
  Reused (not duplicated) by the agent: ``room.by_id``, ``price.compare``,
  ``property.intelligence``.

* **STATE_CHANGING** — every call creates a HUMAN-REVIEW proposal first; the
  participant approves it in chat before anything is applied.
  - ``negotiation.set_boundary`` — record the party's own explicit bounds.
  - ``negotiation.create_offer`` / ``negotiation.counter_offer`` — draft.
  - ``message.send`` — post a drafted offer into the real chat thread.

* **HIGH_RISK**
  - ``negotiation.accept`` — mark the outstanding offer accepted.
  - ``negotiation.finalize`` — close an ACCEPTED negotiation + booking hand-off.

Replay/stale safety and participant ownership are re-verified inside every
executor (see ``services``), so a proposal can never be applied to someone
else's negotiation or an expired/stale offer.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied

from agents.tools import HIGH_RISK, READ_ONLY, STATE_CHANGING, AgentTool, AgentToolRegistry

from . import constants as C
from . import services as S
from .services import _recent_chat_messages, negotiation_payload

_NEGOTIATION_KEY_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 64,
    "description": "The negotiation key (UUID) this action targets",
}
_OFFER_KEY_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "maxLength": 64,
    "description": "The offer key (UUID) this action targets",
}
_AMOUNT_SCHEMA = {
    "type": "number",
    "minimum": C.NegotiationSettings().min_amount,
    "maximum": C.NegotiationSettings().max_amount,
    "description": "Monthly rent amount in BDT (whole taka)",
}


def _guard_enabled():
    if not C.NegotiationSettings().enabled:
        raise S.NegotiationError("feature_disabled")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def _context_executor(context: dict[str, Any], negotiation_key: str) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    payload = negotiation_payload(negotiation, user)
    cfg = C.NegotiationSettings()
    payload["peer_messages"] = _recent_chat_messages(negotiation, user, limit=cfg.context_messages)
    payload["guidance"] = (
        "State: {status}. You are helping the {role}. Use room, insights and "
        "offers strictly as returned — never invent prices, market data, "
        "urgency or the other side's willingness. Draft options only; every "
        "action needs the user's explicit approval in this chat."
    ).format(status=negotiation.status, role=payload.get("my_role") or "participant")
    return {"ok": True, "data": payload}


def _history_executor(context: dict[str, Any], negotiation_key: str) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    rows = list(negotiation.events.select_related("actor").order_by("-created_at")[:50])
    return {
        "ok": True,
        "data": {
            "negotiation_key": str(negotiation.negotiation_key),
            "status": negotiation.status,
            "events": [
                {
                    "event": e.event_type,
                    "actor": getattr(e.actor, "username", "") or "",
                    "detail": dict(e.detail or {}),
                    "at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in rows
            ],
        },
    }


def _set_boundary_executor(
    context: dict[str, Any], negotiation_key: str, boundary: dict[str, Any] | None = None
) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    stored = S.set_constraints(negotiation, user, boundary or {})
    return {"ok": True, "data": {"negotiation_key": negotiation_key, "stored": stored}}


def _draft_executor(
    context: dict[str, Any],
    negotiation_key: str,
    amount: Any,
    message: str = "",
    kind: str = "offer",
    move_in_date: str = "",
    deposit_bdt: Any = None,
) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    result = S.draft_offer(
        negotiation,
        user,
        amount=amount,
        kind=kind,
        message=message,
        move_in_date=move_in_date,
        deposit_bdt=deposit_bdt,
    )
    return {"ok": True, "data": result}


def _create_offer_executor(context: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return _draft_executor(context, kind="offer", **kwargs)


def _counter_offer_executor(context: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return _draft_executor(context, kind="counter", **kwargs)


def _send_executor(
    context: dict[str, Any],
    negotiation_key: str,
    offer_key: str,
    message: str = "",
) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    offer = S.resolve_own_offer(negotiation, offer_key)
    result = S.send_offer(negotiation, user, offer, actor=context.get("actor"), message=message)
    return {"ok": True, "data": result}


def _accept_executor(
    context: dict[str, Any],
    negotiation_key: str,
    offer_key: str,
    note: str = "",
) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    offer = S.resolve_own_offer(negotiation, offer_key)
    result = S.accept_offer(negotiation, user, offer, actor=context.get("actor"), note=note)
    return {"ok": True, "data": result}


def _finalize_executor(
    context: dict[str, Any],
    negotiation_key: str,
    offer_key: str = "",
    note: str = "",
) -> dict[str, Any]:
    user = context.get("user")
    negotiation = S.resolve_negotiation(negotiation_key, user)
    offer = S.resolve_own_offer(negotiation, offer_key) if offer_key else None
    result = S.finalize_negotiation(
        negotiation, user, actor=context.get("actor"), offer=offer, note=note
    )
    return {"ok": True, "data": result}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _wrap(executor):
    """Turn executor errors into grounded error envelopes for the SDK."""

    def wrapped(context, **kwargs):
        try:
            _guard_enabled()
            return executor(context, **kwargs)
        except S.NegotiationNotFound as exc:
            return {"ok": False, "error": str(exc)}
        except PermissionDenied:
            return {"ok": False, "error": "permission_denied"}
        except S.NegotiationError as exc:
            return {"ok": False, "error": str(exc)}

    return wrapped


def register_negotiation_agent_tools() -> None:
    """Register all Phase 19.4 negotiation tools (idempotent)."""

    AgentToolRegistry.register(
        AgentTool(
            name=C.CONTEXT_TOOL,
            description=(
                "Authoritative, participant-scoped context for an active negotiation: "
                "the listing card, price insight, Property Intelligence badge, every "
                "offer (amount/kind/status/sender), the acting user's OWN explicit "
                "boundaries, and the latest real chat messages with the other party. "
                "The counterparty's private boundaries are NEVER included. Use this as "
                "the single source of truth before drafting anything."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key"],
                "properties": {"negotiation_key": _NEGOTIATION_KEY_SCHEMA},
            },
            capability=READ_ONLY,
            executor=_wrap(_context_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.HISTORY_TOOL,
            description=(
                "Auditable timeline of a negotiation (created → boundary set → offers "
                "drafted/sent/accepted etc.). Read-only; use to recap what happened."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key"],
                "properties": {"negotiation_key": _NEGOTIATION_KEY_SCHEMA},
            },
            capability=READ_ONLY,
            executor=_wrap(_history_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.SET_BOUNDARY_TOOL,
            description=(
                "Record the acting user's OWN explicit negotiation boundaries so "
                "future drafts stay inside them (keys: max_budget, min_rent, "
                "deposit_max, deposit_min, move_in_date, other_notes). Private to "
                "that party; never enter the other side's numbers. State-changing: "
                "creates a consent request the user approves."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key", "boundary"],
                "properties": {
                    "negotiation_key": _NEGOTIATION_KEY_SCHEMA,
                    "boundary": {
                        "type": "object",
                        "description": "The acting user's own boundaries",
                    },
                },
            },
            capability=STATE_CHANGING,
            executor=_wrap(_set_boundary_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.CREATE_OFFER_TOOL,
            description=(
                "Draft a concrete rent offer for the acting user (negotiation.create_offer). "
                "It is a DRAFT — nothing is sent to the other party until message.send is "
                "separately approved. The amount must be grounded (listing price, market "
                "comparison, the user's own boundaries); ask the user first, never invent."
            ),
            input_schema=_draft_schema("offer"),
            capability=STATE_CHANGING,
            executor=_wrap(_create_offer_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.COUNTER_OFFER_TOOL,
            description=(
                "Draft a COUNTER offer in response to the other side's outstanding offer. "
                "Same consent + draft semantics as negotiation.create_offer; the offer "
                "only leaves the actor's side after a separate message.send approval."
            ),
            input_schema=_draft_schema("counter"),
            capability=STATE_CHANGING,
            executor=_wrap(_counter_offer_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.SEND_TOOL,
            description=(
                "Send an already-drafted offer (from create_offer/counter_offer) into the "
                "real tenant↔landlord chat thread. Requires its OWN explicit approval: "
                "sending is an outbound, message-level action. The offer becomes SENT and "
                "the other party is notified. Never send without the user confirming the "
                "exact amount and message text."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key", "offer_key"],
                "properties": {
                    "negotiation_key": _NEGOTIATION_KEY_SCHEMA,
                    "offer_key": _OFFER_KEY_SCHEMA,
                    "message": {
                        "type": "string",
                        "maxLength": C.NegotiationSettings().max_message_len,
                        "default": "",
                        "description": "Optional override of the user-facing message",
                    },
                },
            },
            capability=STATE_CHANGING,
            executor=_wrap(_send_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.ACCEPT_TOOL,
            description=(
                "HIGH RISK: accept the other side's outstanding SENT offer, which moves "
                "the negotiation to ACCEPTED. Never invents acceptance — the user gives "
                "an in-chat APPROVAL for the proposal this call creates. No booking, "
                "payment or deposit is created by accepting."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key", "offer_key"],
                "properties": {
                    "negotiation_key": _NEGOTIATION_KEY_SCHEMA,
                    "offer_key": _OFFER_KEY_SCHEMA,
                    "note": {"type": "string", "maxLength": 500, "default": ""},
                },
            },
            capability=HIGH_RISK,
            executor=_wrap(_accept_executor),
            owner="rentora.negotiation_agent",
        )
    )

    AgentToolRegistry.register(
        AgentTool(
            name=C.FINALIZE_TOOL,
            description=(
                "HIGH RISK: close an ACCEPTED negotiation and hand both parties to the "
                "booking flow (notification with action link). The agent NEVER books, "
                "charges, or edits the room. Requires the user's explicit in-chat "
                "approval of the proposal; idempotent on already-closed negotiations."
            ),
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["negotiation_key"],
                "properties": {
                    "negotiation_key": _NEGOTIATION_KEY_SCHEMA,
                    "offer_key": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                        "default": "",
                        "description": "Optional accepted offer key",
                    },
                    "note": {"type": "string", "maxLength": 500, "default": ""},
                },
            },
            capability=HIGH_RISK,
            executor=_wrap(_finalize_executor),
            owner="rentora.negotiation_agent",
        )
    )


def _draft_schema(kind: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["negotiation_key", "amount"],
        "properties": {
            "negotiation_key": _NEGOTIATION_KEY_SCHEMA,
            "amount": _AMOUNT_SCHEMA,
            "message": {
                "type": "string",
                "maxLength": C.NegotiationSettings().max_message_len,
                "default": "",
                "description": "User-facing draft text (used as the sent message)",
            },
            "move_in_date": {
                "type": "string",
                "maxLength": 10,
                "default": "",
                "description": "Optional move-in date (YYYY-MM-DD)",
            },
            "deposit_bdt": {
                "type": "number",
                "minimum": 0,
                "description": "Optional advance/deposit in BDT",
            },
            "kind": {
                "type": "string",
                "enum": ["offer", "counter"],
                "default": kind,
                "description": "offer (initial) or counter (response) — fixed for this tool",
            },
        },
    }
