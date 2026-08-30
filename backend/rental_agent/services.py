"""Rentora AI Rental Agent services — Phase 19.2.

* Public, grounded room cards + insight payloads for the domain tools and the
  chat API (never invented data — everything is read from stored Room rows).
* Tenant self-consent for ``bookmark.create``: a proposal may be approved and
  applied by its **conversation owner** alone (the SDK's general rule reserves
  approval for staff; this phase deliberately re-reviews that for the
  tenant's *own* bookmark using the same locked, exactly-once ``apply_proposal``
  mechanism). Ownership is verified server-side, never trusted from arguments.
* Conversation payloads for the chat API: enriched transcript (cards attached
  to the assistant message that follows each tool result), pending/applied
  proposals with their room cards, deterministic grounded suggestion chips and
  latest run status.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .tools import BOOKMARK_TOOL, ROOM_TOOL, SEARCH_TOOL


class RentalAgentError(Exception):
    """Base for Phase 19.2 service errors."""


class ConsentError(RentalAgentError):
    """A tenant self-consent could not be completed (never rethrows as-is to
    the client — views map it to a bounded plain-language error)."""


# ---------------------------------------------------------------------------
# Grounded cards + insights
# ---------------------------------------------------------------------------


def room_card(room) -> dict[str, Any]:
    """Public card for one Room — every value is a stored room field."""
    primary = room.images.order_by("-is_primary").first() if hasattr(room, "images") else None
    return {
        "id": room.pk,
        "title": room.title,
        "price_bdt": float(room.price),
        "price_text": f"৳{int(room.price):,}",
        "currency": "BDT",
        "area": room.area,
        "area_display": room.get_area_display(),
        "room_type": room.room_type,
        "room_type_display": room.get_room_type_display(),
        "gender_preference": room.gender_preference,
        "size_sqft": room.size_sqft,
        "amenities": list(room.amenities or []),
        "address": (room.address or "")[:240],
        "verified": bool(room.verified),
        "featured": bool(room.is_featured or room.tier in ("featured", "premium")),
        "available": bool(room.is_available),
        "lat": float(room.lat),
        "lng": float(room.lng),
        "image": primary.image.url if primary else None,
        "url": f"/rooms/{room.pk}/",
    }


def _property_badge(room) -> dict[str, Any] | None:
    """Lightweight Property Intelligence badge (Phase 19.1 public payload),
    honouring the same serializer feature flag and failing soft."""
    if not getattr(settings, "PROPERTY_INTELLIGENCE_SERIALIZER_ENABLED", True):
        return None
    try:
        from property_intelligence.engine import get_property_intelligence, public_payload

        payload = public_payload(get_property_intelligence(room))
    except Exception:
        return None
    return {
        key: payload.get(key)
        for key in (
            "room_id",
            "score",
            "confidence",
            "confidence_reasons",
            "strengths",
            "suggestions",
            "disclaimer",
        )
    }


def room_insights(room) -> dict[str, Any]:
    """Grounded insight block for one room: price comparison, nearby landmarks
    and the Property Intelligence badge."""
    from pricing.services.insight import get_price_insight
    from rooms.geo import landmarks_within
    from rooms.landmarks import ALL_LANDMARKS

    insight = get_price_insight(room)
    price: dict[str, Any] = {}
    if insight is None:
        price = {"available": False, "reason": "no_market_data"}
    else:
        price = {
            "available": True,
            "listed_price": insight["your_price"],
            "market_average": insight["avg_price"],
            "percentage_diff": insight["percentage_diff"],
            "classification": insight["classification"],
            "message": insight["message"],
            "sample_size": insight["sample_size"],
        }

    landmarks = [
        {
            "key": lm.key,
            "name": lm.name,
            "kind": lm.kind.value,
            "distance_km": round(distance, 2),
        }
        for lm, distance in landmarks_within(float(room.lat), float(room.lng), 3.0, ALL_LANDMARKS)
    ][:6]

    return {
        "price": price,
        "nearby_landmarks": landmarks,
        "property_intelligence": _property_badge(room),
    }


def proposal_room_card(proposal) -> dict[str, Any] | None:
    """Room card for a booking proposal (from its stored action/result), or
    None if the referenced room is gone. Grounded: never fabricated."""
    from rooms.models import Room

    room_id = None
    action = proposal.action or {}
    arguments = action.get("arguments") or {}
    if isinstance(arguments, dict) and arguments.get("room_id"):
        room_id = int(arguments["room_id"])
    if room_id is None:
        result = proposal.application_result or {}
        data = result.get("data") or {}
        if isinstance(data, dict) and data.get("room_id"):
            room_id = int(data["room_id"])
    if room_id is None:
        return None
    room = Room.objects.filter(pk=room_id).first()
    return room_card(room) if room else None


def is_bookmark_proposal(proposal) -> bool:
    action = proposal.action or {}
    return bool(action.get("tool") == BOOKMARK_TOOL)


# ---------------------------------------------------------------------------
# Tenant self-consent (bookmark.create)
# ---------------------------------------------------------------------------


def _consent_owner(proposal):
    run = proposal.run
    if run is None or run.conversation is None:
        raise ConsentError("no_owner_conversation")
    owner = run.conversation.user
    if owner is None:
        raise ConsentError("no_owner_conversation")
    return owner


def _expire_sibling_bookmark_proposals(proposal) -> None:
    """Dedupe: once a room is saved, sibling PENDING bookmark requests for
    the same room by the same conversation owner become stale — expire them,
    even when they live in a different chat thread (one save per room)."""
    from agents.models import AgentProposal
    from agents.services import ProposalStatus

    owner = proposal.run.conversation.user
    sibling = AgentProposal.objects.filter(
        run__conversation__user=owner,
        proposal_type=BOOKMARK_TOOL,
        status=ProposalStatus.PENDING,
    ).exclude(pk=proposal.pk)
    for row in sibling:
        arguments = row.action.get("arguments") or {}
        if int(arguments.get("room_id", -1)) == int(
            (proposal.action.get("arguments") or {}).get("room_id", -2)
        ):
            row.status = ProposalStatus.EXPIRED
            row.save(update_fields=["status"])


@transaction.atomic
def self_consent_and_apply(user, proposal):
    """Approve + apply a *bookmark* proposal as its conversation owner.

    Idempotent and replay-safe: an already-APPLIED proposal is a no-op (the
    wishlist table's unique (user, room) constraint guarantees a single save
    even across races). Rejected / expired proposals are never actionable.
    Execution goes through ``agents.services.apply_proposal`` inside the same
    transaction — the exact once-only mechanism the SDK uses for reviewers.
    """
    from agents.models import AgentProposal
    from agents.services import apply_proposal

    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        return locked
    if locked.status != "pending":
        raise ConsentError(f"cannot_consent_{locked.status}")

    owner = _consent_owner(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")
    if not is_bookmark_proposal(locked):
        raise ConsentError("unsupported_proposal_type")
    if locked.is_expired:
        raise ConsentError("expired")

    locked.status = "approved"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.meta = {
        **locked.meta,
        "consent": "tenant_self_consent",
        "approval_note": "approved by the conversation owner (bookmark consent)",
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=user,
            action="agent.proposal.self_consented",
            target=locked,
            detail=f"tenant self-consent for bookmark proposal {locked.proposal_key}",
        )
    except Exception:
        pass

    _expire_sibling_bookmark_proposals(locked)
    return apply_proposal(locked, actor=user)


@transaction.atomic
def self_reject(user, proposal, *, reason: str = ""):
    """Reject a pending *bookmark* proposal as its conversation owner."""
    from agents.models import AgentProposal

    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        raise ConsentError("cannot_reject_applied")
    if locked.status != "pending":
        raise ConsentError(f"cannot_reject_{locked.status}")

    owner = _consent_owner(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")
    if not is_bookmark_proposal(locked):
        raise ConsentError("unsupported_proposal_type")
    if locked.is_expired:
        raise ConsentError("expired")

    locked.status = "rejected"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.rejection_reason = (reason or "")[:2000]
    locked.meta = {
        **locked.meta,
        "consent": "tenant_self_reject",
        "reject_reason": (reason or "")[:500],
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=user,
            action="agent.proposal.self_rejected",
            target=locked,
            detail=f"tenant rejected bookmark proposal {locked.proposal_key}",
        )
    except Exception:
        pass
    return locked


# ---------------------------------------------------------------------------
# Conversation payload (enrichment + chips)
# ---------------------------------------------------------------------------


def _parse_tool_result(content: str) -> dict[str, Any] | None:
    try:
        value = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _cards_from_tool_result(tool_name: str, env: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not env or not env.get("ok"):
        return []
    data = env.get("data")
    if not isinstance(data, dict):
        return []
    if tool_name == SEARCH_TOOL:
        rooms = data.get("rooms") or []
        return [c for c in rooms if isinstance(c, dict) and c.get("id")]
    if tool_name == ROOM_TOOL and data.get("available", True) is not False:
        room_id = data.get("id") or data.get("room_id")
        if room_id:
            from rooms.models import Room

            room = Room.objects.filter(pk=room_id).first()
            if room:
                return [room_card(room)]
    if tool_name == BOOKMARK_TOOL:
        room_id = data.get("room_id")
        if room_id:
            from rooms.models import Room

            room = Room.objects.filter(pk=room_id).first()
            if room:
                return [room_card(room)]
    return []


def _walk_messages(conversation) -> list[dict[str, Any]]:
    """Rebuild the user-facing transcript: user + assistant *text* messages,
    with room cards attached to the assistant message that follows the
    corresponding tool result. Tool/frame protocol rows are folded away."""
    messages = list(conversation.messages.order_by("sequence"))
    frames: dict[str, str] = {}
    pending_cards: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []

    for msg in messages:
        meta = msg.metadata or {}
        if msg.role == "assistant" and meta.get("tool_call"):
            frames[meta.get("tool_call_id", "")] = meta["tool_call"].get("name", "")
            continue
        if msg.role == "tool":
            env = _parse_tool_result(msg.content)
            tool_name = frames.get(meta.get("tool_call_id", ""), "")
            if tool_name in (SEARCH_TOOL, ROOM_TOOL, BOOKMARK_TOOL):
                pending_cards.extend(_cards_from_tool_result(tool_name, env))
            continue
        if msg.role != "user" and msg.role != "assistant":
            continue
        if msg.role == "assistant":
            out.append(
                {
                    "id": msg.pk,
                    "role": msg.role,
                    "content": msg.content or "",
                    "created_at": msg.timestamp.isoformat() if msg.timestamp else None,
                    "cards": pending_cards,
                }
            )
            pending_cards = []
        else:
            out.append(
                {
                    "id": msg.pk,
                    "role": msg.role,
                    "content": msg.content or "",
                    "created_at": msg.timestamp.isoformat() if msg.timestamp else None,
                    "cards": [],
                }
            )
    return out


def _last_tool_result(conversation, tool_name: str) -> dict[str, Any] | None:
    frames: dict[str, str] = {}
    last: dict[str, Any] | None = None
    for msg in conversation.messages.order_by("sequence"):
        meta = msg.metadata or {}
        if msg.role == "assistant" and meta.get("tool_call"):
            frames[meta.get("tool_call_id", "")] = meta["tool_call"].get("name", "")
        elif msg.role == "tool" and frames.get(meta.get("tool_call_id", "")) == tool_name:
            env = _parse_tool_result(msg.content)
            if env:
                last = env
    return last


def _search_filter_chip(label: str, text: str) -> dict[str, str]:
    return {"label": label, "text": text}


def suggestion_chips(conversation) -> list[dict[str, str]]:
    """Deterministic, grounded next-step chips derived only from the last
    ``search.list_rooms`` result (its filters and any real returned rooms)."""
    env = _last_tool_result(conversation, SEARCH_TOOL)
    if not env or not env.get("ok"):
        return [
            _search_filter_chip("রুম খুঁজো", "ধানমন্ডি বা মিরপুরে সিঙ্গেল রুম খুঁজে দেখো"),
            _search_filter_chip("Budget", "১০০০০ টাকার মধ্যে রুম দেখাও"),
        ]

    data = env.get("data") or {}
    filters = data.get("filters") or {}
    rooms = data.get("rooms") or []
    chips: list[dict[str, str]] = []

    first = rooms[0] if rooms else None
    if first:
        chips.append(_search_filter_chip("বিস্তারিত", f"রুম #{first['id']} সম্পর্কে বিস্তারিত বলো"))
        chips.append(_search_filter_chip("ভাড়া", f"রুম #{first['id']} কি দামে যুক্তিসঙ্গত?"))
    chips.append(_search_filter_chip("আরও রুম", "আরও কয়েকটা রুম দেখাও"))

    area = (filters.get("areas") or [None])[0]
    budget = filters.get("budget_max")
    room_type = filters.get("room_type")
    if area and budget:
        chips.append(_search_filter_chip("অনুরূপ", f"{area}-এ {budget} টাকার মধ্যে আরও রুম দেখাও"))
    elif budget:
        chips.append(_search_filter_chip("Budget", f"{budget} টাকার মধ্যে আরও রুম দেখাও"))
    if area:
        chips.append(_search_filter_chip("কমিউট", f"{area} থেকে Uttara যেতে কত সময় লাগে?"))
    if room_type:
        chips.append(_search_filter_chip("বদল", f"হঠাৎ {room_type} রুমের লিস্ট দেখা যাবে"))
    return chips[:5]


def _run_payload(run) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "key": str(run.run_key),
        "status": run.status,
        "termination_reason": run.termination_reason or "",
        "error_message": (run.error_message or "")[:400],
        "turn_count": run.turn_count,
        "tool_call_count": run.tool_call_count,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _proposal_payload(proposal) -> dict[str, Any]:
    run = proposal.run
    return {
        "key": str(proposal.proposal_key),
        "tool": (proposal.action or {}).get("tool", ""),
        "status": proposal.status,
        "approval_required": proposal.approval_required,
        "room": proposal_room_card(proposal),
        "summary": proposal.summary[:300],
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
        "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
        "conversation_id": run.conversation_id if run else None,
    }


def conversation_payload(conversation) -> dict[str, Any]:
    """Enriched payload the chat UI renders (no side effects)."""
    agent = conversation.agent
    latest_run = conversation.runs.order_by("-created_at").first()

    proposals = []
    if conversation.pk:
        from agents.models import AgentProposal

        status_rank = {
            "pending": 0,
            "applied": 1,
            "approved": 2,
            "rejected": 3,
            "expired": 4,
            "failed": 5,
        }
        qs = list(AgentProposal.objects.filter(run__conversation=conversation))
        qs.sort(key=lambda p: (status_rank.get(p.status, 9), -p.pk))
        proposals = [_proposal_payload(p) for p in qs[:20]]

    feature_enabled = False
    if agent is not None and agent.feature_id is not None:
        from ai_intelligence.services import is_feature_available

        try:
            feature_enabled = is_feature_available(agent.feature.feature_id, user=conversation.user)
        except Exception:
            feature_enabled = False

    return {
        "id": conversation.pk,
        "title": conversation.title or "",
        "status": conversation.status,
        "feature_enabled": feature_enabled,
        "agent": {
            "key": agent.key if agent else "",
            "name": agent.name if agent else "Rentora Agent",
            "description": agent.description if agent else "",
        },
        "latest_run": _run_payload(latest_run),
        "messages": _walk_messages(conversation),
        "proposals": proposals,
        "suggestions": suggestion_chips(conversation),
    }
