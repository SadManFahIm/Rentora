"""Listing Autopilot services (Phase 19.3).

Owns the weekly run: builds the deterministic analysis per eligible listing,
persists a ``ListingAnalysis`` snapshot (idempotent per room+week), and emits
typed ``AgentProposal`` rows through the Phase 19.0 SDK. It also exposes the
landlord-facing proposal surface and the landlord *self-consent* logic that
reuses the SDK's locked, exactly-once ``apply_proposal`` — mirroring the
tenant self-consent pattern established in Phase 19.2.

Lifecycle
---------
PENDING → APPROVED → APPLIED | FAILED
       → REJECTED
       → EXPIRED (the SDK's ``expire_proposals`` beat task)

* Proposals are PENDING when created (the AI never self-approves).
* A landlord (the proposal's conversation owner) approves and applies their
  own proposal. Ownership is verified server-side; the AI/agent can never
  approve for them.
* Applying is replay-safe: ``apply_proposal`` is a no-op for an already
  APPLIED proposal and refuses any non-APPROVED status.

Idempotency guarantees
----------------------
* One ``ListingAnalysis`` per (room, week_key) via a unique constraint.
* No duplicate *unresolved* proposal per (room, proposal_type): a PENDING or
  APPROVED proposal of the same type for the same room suppresses a new one.
  Resolved proposals (applied, rejected, expired, failed) free the slot so the
  next week can (re)recommend.
* Per-file isolation: the weekly task wraps each room's analysis in its own
  transaction so one failing listing never aborts the whole run.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from agents.models import Agent, AgentConversation, AgentProposal, AgentRun, AgentToolCall
from audit.services import log_action

from . import constants as C
from .analysis import analyze_room, grounding_key
from .models import ListingAnalysis


class AutopilotError(Exception):
    """Base for Phase 19.3 service errors (views map to bounded responses)."""


class ConsentError(AutopilotError):
    """A landlord self-consent could not be completed."""


def week_key(dt=None) -> str:
    """ISO year-week, e.g. ``2026-W35`` — the idempotency window."""
    value = dt or timezone.now()
    return f"{value.isocalendar()[0]}-W{value.isocalendar()[1]:02d}"


def get_agent():
    return Agent.objects.filter(key=C.AGENT_KEY).first()


def _own_conversation(landlord) -> AgentConversation:
    """One durable autopilot conversation per landlord (created on demand)."""
    agent = get_agent()
    if agent is not None:
        conv = (
            AgentConversation.objects.filter(agent=agent, user=landlord, title=C.AGENT_NAME)
            .order_by("pk")
            .first()
        )
        if conv is not None:
            return conv
    # Fall back to any autopilot conversation the landlord owns.
    conv = (
        AgentConversation.objects.filter(agent=agent, user=landlord, agent__key=C.AGENT_KEY)
        .order_by("pk")
        .first()
    )
    if conv is not None:
        return conv
    return AgentConversation.objects.create(
        agent=agent,
        user=landlord,
        title=C.AGENT_NAME,
        metadata={"driver": "weekly_autopilot"},
    )


def _create_run(landlord, room) -> AgentRun:
    """A synthetic, completed run carrying one listing's weekly proposals."""
    conv = _own_conversation(landlord)
    agent = conv.agent
    run = AgentRun.objects.create(
        run_key=uuid.uuid4(),
        conversation=conv,
        agent=agent,
        user=landlord,
        created_by=landlord,
        status="completed",
        started_at=timezone.now(),
        completed_at=timezone.now(),
        metadata={"week_key": week_key(), "room_id": room.pk, "driver": "weekly_autopilot"},
    )
    if agent is not None:
        run.prompt_key = agent.prompt_key or ""
    run.save(update_fields=["prompt_key"])
    return run


def _existing_unresolved(room, proposal_type: str) -> AgentProposal | None:
    return (
        AgentProposal.objects.filter(
            run__conversation__user__isnull=False,
            proposal_type=proposal_type,
            status__in=["pending", "approved"],
            meta__room_id=str(room.pk),
        )
        .order_by("-created_at")
        .first()
    )


def _sync_run_status(run: AgentRun) -> None:
    run.refresh_from_db()
    run.status = "completed"
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at"])


def _slug(proposal_type: str) -> str:
    return proposal_type.lower().replace("_", "-")


def _proposal_ttl_seconds() -> int:
    return int(getattr(settings, "AGENTS_PROPOSAL_TTL_SECONDS", 86400))


def _proposal_title(proposal_type: str, room) -> str:
    nouns = {
        "TITLE_UPDATE": "title",
        "DESCRIPTION_UPDATE": "description",
        "AMENITY_UPDATE": "amenities",
        "PHOTO_RECOMMENDATION": "photos",
        "PRICE_UPDATE": "price",
        "LISTING_RENEWAL": "renewal",
    }
    label = nouns.get(proposal_type, proposal_type.lower().replace("_", " ").title())
    return f"{label.capitalize()} — Listing #{room.pk}"


def _proposal_summary(proposal_type: str, rec: dict[str, Any]) -> str:
    if proposal_type == "TITLE_UPDATE":
        return f"Rename to: {rec.get('suggested_title', '')[:200]}"
    if proposal_type == "DESCRIPTION_UPDATE":
        return "A fuller, grounded description draft is ready to review."
    if proposal_type == "AMENITY_UPDATE":
        return "Add amenities: " + ", ".join(rec.get("suggested_additions", []))
    if proposal_type == "PHOTO_RECOMMENDATION":
        return "Photo recommendation — " + "; ".join(rec.get("suggested_actions", []))
    if proposal_type == "PRICE_UPDATE":
        price = rec.get("suggested_price")
        try:
            formatted = f"৳{int(Decimal(str(price))):,}"
        except (TypeError, ValueError):
            formatted = str(price)
        return f"Price suggestion: {rec.get('direction', '')} to {formatted}"
    if proposal_type in ("LISTING_RENEWAL", "LISTENING_RENEWAL"):
        return "Renew the listing to refresh its recency in search."
    return "Listing Autopilot recommendation pending review."


def _proposal_arguments(proposal_type: str, rec: dict[str, Any]) -> dict[str, Any]:
    """Ground the proposal's action arguments (what apply will execute)."""
    base = {"room_id": rec.get("room_id"), "grounding_key": rec.get("grounding_key", "")}
    if proposal_type == "TITLE_UPDATE":
        base["title"] = rec.get("suggested_title", "")
    elif proposal_type == "DESCRIPTION_UPDATE":
        base["description"] = rec.get("suggested_description", "")
    elif proposal_type == "AMENITY_UPDATE":
        base["add_amenities"] = rec.get("suggested_additions", [])
    elif proposal_type == "PHOTO_RECOMMENDATION":
        base["suggested_actions"] = rec.get("suggested_actions", [])
        base["suggested_amenities"] = rec.get("suggested_amenities", [])
    elif proposal_type == "PRICE_UPDATE":
        base["new_price"] = rec.get("suggested_price")
        base["direction"] = rec.get("direction", "")
    return base


def _stale_checks(room, proposal_type: str) -> dict[str, str]:
    """Per-field checksums for the fields this proposal will overwrite. Only a
    landlord edit to one of these exact fields since analysis blocks apply."""
    from .analysis import field_grounding, stale_fields

    return {
        field: field_grounding(room, (field,))
        for field in stale_fields(proposal_type)
        if field in ("title", "description", "amenities", "price")
    }


def _emit_proposal(
    run: AgentRun,
    room,
    rec: dict[str, Any],
    *,
    actor=None,
) -> AgentProposal | None:
    """Create a typed proposal for one recommendation. Idempotent: does not
    duplicate an unresolved proposal of the same type for the same room."""
    proposal_type = rec.get("type", "")
    if not isinstance(proposal_type, str) or proposal_type not in C.PROPOSAL_TYPES:
        return None
    if _existing_unresolved(room, proposal_type):
        return None

    # The recommendation must always reference the owning room — sourced from
    # the argument, never trusted from the caller's dict.
    rec = {**rec, "room_id": room.pk}
    tool_name = f"listing.autopilot.apply.{_slug(proposal_type)}"
    arguments = _proposal_arguments(proposal_type, rec)
    arguments["stale_checks"] = _stale_checks(room, proposal_type)

    with transaction.atomic():
        tool_call = AgentToolCall.objects.create(
            run=run,
            tool_name=tool_name,
            arguments=arguments,
            execution_status="proposed",
            permission_decision="proposed",
            actor=actor,
            result={},
        )
        proposal = AgentProposal.objects.create(
            proposal_key=uuid.uuid4(),
            run=run,
            tool_call=tool_call,
            proposal_type=proposal_type,
            title=_proposal_title(proposal_type, room),
            summary=_proposal_summary(proposal_type, rec),
            action={
                "tool": tool_name,
                "arguments": arguments,
                "tool_call_id": str(tool_call.pk),
            },
            status="pending",
            approval_required="any_staff",
            created_by=actor,
            expires_at=timezone.now() + timezone.timedelta(seconds=_proposal_ttl_seconds()),
            meta={
                "room_id": str(room.pk),
                "week_key": run.metadata.get("week_key", ""),
                "grounding_key": rec.get("grounding_key", "") or "",
                "stale_checks": arguments.get("stale_checks", {}),
                "recommendation": rec,
            },
        )
    with suppress(Exception):
        log_action(
            actor=actor,
            action="autopilot.proposal.created",
            target=proposal,
            detail=f"{proposal_type} for room {room.pk}",
        )
    return proposal


def _build_summary(analysis: dict[str, Any]) -> str:
    if not analysis["eligible"]:
        return "Listing is not eligible for autopilot recommendations this week."
    n = len(analysis["recommendations"])
    if n == 0:
        return "This listing is in good shape — no recommendations this week."
    types = ", ".join(sorted({r["type"] for r in analysis["recommendations"]}))
    return f"{n} recommendation(s): {types}."


def analyze_and_propose(
    landlord,
    room,
    *,
    week: str = "",
    privilege_bypass: bool = False,
    actor=None,
) -> ListingAnalysis:
    """Analyze one room, persist the snapshot, and emit proposals.

    Idempotent: if a ``ListingAnalysis`` already exists for (room, week) no new
    proposals are created (existing PENDING ones stay authoritative until
    resolved). Returns the (created or existing) snapshot.
    """
    week = week or week_key()
    analysis = analyze_room(room, privilege_bypass=privilege_bypass)

    # Ground the proposals on a pristine DB read of the room, not the possibly
    # in-memory instance the analysis ran on — guarantees apply-time staleness
    # checks compare against the exact stored row (immune to engine-side
    # in-memory drift across processes).
    from rooms.models import Room

    stamp = grounding_key(Room.objects.get(pk=room.pk))
    if stamp:
        analysis["grounding_key"] = stamp

    def _int(value):
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    obj, created = ListingAnalysis.objects.get_or_create(
        room=room,
        week_key=week,
        defaults={
            "eligible": analysis["eligible"],
            "eligibility_blocks": analysis["eligibility_blocks"],
            "quality_score": _int(analysis["listing_quality"].get("score")),
            "quality_level": analysis["listing_quality"].get("level") or "",
            "property_score": _int(analysis["property_intelligence"].get("score")),
            "property_confidence": analysis["property_intelligence"].get("confidence") or "",
            "price_direction": analysis["price"].get("direction", "hold"),
            "suggested_price": analysis["price"].get("suggested") or None,
            "photo_count": analysis["photo_count"],
            "stale_days": analysis["stale_days"],
            "grounding_key": analysis["grounding_key"],
            "payload": analysis,
            "summary": _build_summary(analysis),
        },
    )
    if created and analysis["eligible"]:
        run = _create_run(landlord, room)
        for rec in analysis["recommendations"]:
            rec["room_id"] = room.pk
            rec["grounding_key"] = analysis["grounding_key"]
            _emit_proposal(run, room, rec, actor=actor)
        _sync_run_status(run)
    return obj


# ---------------------------------------------------------------------------
# Landlord-facing proposal surface
# ---------------------------------------------------------------------------


def landlord_proposals(
    landlord, *, status: str = "pending", limit: int = 50
) -> list[AgentProposal]:
    qs = AgentProposal.objects.filter(
        run__conversation__user=landlord,
        run__conversation__agent__key=C.AGENT_KEY,
    ).select_related("run", "run__conversation", "tool_call")
    if status:
        qs = qs.filter(status=status)
    return list(qs.order_by("-created_at")[:limit])


def landlord_analyses(landlord, *, limit: int = 30) -> list[ListingAnalysis]:
    return list(
        ListingAnalysis.objects.filter(room__owner=landlord, room__isnull=False)
        .select_related("room")
        .order_by("-created_at")[:limit]
    )


def proposal_payload(proposal: AgentProposal) -> dict[str, Any]:
    run = proposal.run
    arguments = (proposal.action or {}).get("arguments") or {}
    room_id = arguments.get("room_id")
    return {
        "key": str(proposal.proposal_key),
        "type": proposal.proposal_type,
        "status": proposal.status,
        "title": proposal.title,
        "summary": proposal.summary[:500],
        "room_id": room_id,
        "grounding_key": (proposal.meta or {}).get("grounding_key", ""),
        "recommendation": (proposal.meta or {}).get("recommendation", {}),
        "arguments": arguments,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "expires_at": proposal.expires_at.isoformat() if proposal.expires_at else None,
        "reviewed_at": proposal.reviewed_at.isoformat() if proposal.reviewed_at else None,
        "applied_at": proposal.applied_at.isoformat() if proposal.applied_at else None,
        "application_result": proposal.application_result,
        "rejection_reason": proposal.rejection_reason,
        "conversation_id": run.conversation_id if run else None,
    }


# ---------------------------------------------------------------------------
# Landlord self-consent (approve+apply / reject) — reuses SDK locked apply
# ---------------------------------------------------------------------------


def _consent_owner(proposal):
    run = proposal.run
    if run is None or run.conversation is None:
        raise ConsentError("no_owner_conversation")
    owner = run.conversation.user
    if owner is None:
        raise ConsentError("no_owner_conversation")
    return owner


def _is_autopilot_proposal(proposal) -> bool:
    return bool((proposal.action or {}).get("tool", "").startswith("listing.autopilot.apply"))


def _room_from_proposal(proposal):
    arguments = (proposal.action or {}).get("arguments") or {}
    room_id = arguments.get("room_id")
    if room_id is None:
        return None
    from rooms.models import Room

    return Room.objects.filter(pk=room_id).first()


def _check_owner_owns_room(owner, room) -> None:
    """The landlord must own the referenced room — never trust arguments."""
    if room is None:
        raise ConsentError("room_missing")
    if getattr(room, "owner_id", None) != getattr(owner, "pk", None):
        raise PermissionDenied("not_room_owner")


@transaction.atomic
def autopilot_approve_and_apply(user, proposal) -> AgentProposal:
    """Approve + apply a *listing autopilot* proposal as its landlord owner.

    Idempotent and replay-safe: an already-APPLIED proposal is a no-op; a
    rejected/expired proposal is never actionable. Execution delegates to
    ``agents.services.apply_proposal`` (the exact once-only mechanism the SDK
    uses for reviewers) inside the same transaction, after the ownership and
    stale-grounding checks enforced here.
    """
    from agents.services import apply_proposal

    # The autopilot never runs an agent session (it creates proposals directly
    # on the schedule), so we must guarantee the Tool Registry is warm before
    # the SDK's apply path resolves the proposal's tool. Idempotent.
    from agents.tools import register_builtin_tools

    register_builtin_tools()

    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        return locked
    if locked.status != "pending":
        raise ConsentError(f"cannot_consent_{locked.status}")

    owner = _consent_owner(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")
    if not _is_autopilot_proposal(locked):
        raise ConsentError("unsupported_proposal_type")
    room = _room_from_proposal(locked)
    _check_owner_owns_room(owner, room)
    if locked.is_expired:
        raise ConsentError("expired")

    locked.status = "approved"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.meta = {
        **locked.meta,
        "consent": "landlord_self_consent",
        "approval_note": "approved by the listing owner (autopilot consent)",
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "meta"])
    with suppress(Exception):
        log_action(
            actor=user,
            action="autopilot.proposal.self_consented",
            target=locked,
            detail=f"landlord approved autopilot proposal {locked.proposal_key}",
        )

    return apply_proposal(locked, actor=user)


@transaction.atomic
def autopilot_reject(user, proposal, *, reason: str = "") -> AgentProposal:
    """Reject a pending autopilot proposal as its landlord owner."""
    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == "applied":
        raise ConsentError("cannot_reject_applied")
    if locked.status != "pending":
        raise ConsentError(f"cannot_reject_{locked.status}")

    owner = _consent_owner(locked)
    if getattr(user, "pk", None) != owner.pk:
        raise PermissionDenied("not_proposal_owner")
    if not _is_autopilot_proposal(locked):
        raise ConsentError("unsupported_proposal_type")
    room = _room_from_proposal(locked)
    _check_owner_owns_room(owner, room)
    if locked.is_expired:
        raise ConsentError("expired")

    locked.status = "rejected"
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = user
    locked.rejection_reason = (reason or "")[:2000]
    locked.meta = {
        **locked.meta,
        "consent": "landlord_self_reject",
        "reject_reason": (reason or "")[:500],
    }
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason", "meta"])
    with suppress(Exception):
        log_action(
            actor=user,
            action="autopilot.proposal.rejected",
            target=locked,
            detail=f"landlord rejected autopilot proposal {locked.proposal_key}",
        )
    return locked
