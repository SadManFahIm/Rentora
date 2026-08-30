"""Agent SDK services — registry CRUD, run plumbing, proposal lifecycle
and evaluation hook — Phase 19.0."""

import uuid
from contextlib import suppress
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .errors import AgentRegistryError, ProposalError
from .models import (
    Agent,
    AgentConversation,
    AgentMessage,
    AgentProposal,
    AgentRun,
    AgentToolCall,
    ProposalStatus,
)
from .tools import RESULT_OK, AgentToolRegistry

__all__ = [
    "append_message",
    "apply_proposal",
    "approve_proposal",
    "create_agent_eval_run",
    "create_conversation",
    "create_proposal",
    "create_run",
    "expire_proposals",
    "get_agent",
    "list_agents",
    "notify_run_outcome",
    "register_agent",
    "reject_proposal",
]


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


def get_agent(key: str) -> Agent | None:
    try:
        return Agent.objects.get(key=key)
    except Agent.DoesNotExist:
        return None


def list_agents(*, status: str = "") -> list[Agent]:
    qs = Agent.objects.all()
    if status:
        qs = qs.filter(status=status)
    return list(qs)


def register_agent(
    key: str,
    name: str,
    description: str = "",
    *,
    status: str = "disabled",
    audience: str = "staff",
    permission: str = "operator",
    feature_id: str = "",
    prompt_key: str = "",
    provider: str = "",
    model_name: str = "",
    system_instructions: str = "",
    enabled_tools: list[str] | None = None,
    max_turns: int | None = None,
    max_tool_calls: int | None = None,
    max_tokens: int | None = None,
    max_cost_usd: Decimal | None = None,
    timeout_seconds: int | None = None,
    metadata: dict | None = None,
) -> Agent:
    """Idempotent upsert (create-or-update) of an agent definition.

    New agents default to ``disabled`` unless an explicit status is given, so
    registrations are never live by accident.
    """
    defaults: dict = {
        "name": name,
        "description": description,
        "status": status,
        "audience": audience,
        "permission": permission,
        "prompt_key": prompt_key,
        "provider": provider,
        "model_name": model_name,
        "system_instructions": system_instructions,
        "enabled_tools": enabled_tools or [],
        "max_turns": max_turns,
        "max_tool_calls": max_tool_calls,
        "max_tokens": max_tokens,
        "max_cost_usd": max_cost_usd,
        "timeout_seconds": timeout_seconds,
        "metadata": metadata or {},
    }
    if feature_id:
        from ai_intelligence.models import AIFeatureRegistry

        feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
        defaults["feature"] = feature
    agent, _ = Agent.objects.update_or_create(key=key, defaults=defaults)
    return agent


# ---------------------------------------------------------------------------
# Conversations / runs
# ---------------------------------------------------------------------------


def create_conversation(
    agent: Agent,
    user,
    *,
    title: str = "",
    metadata: dict | None = None,
) -> AgentConversation:
    if agent.status != "active":
        raise AgentRegistryError("agent_not_active")
    return AgentConversation.objects.create(
        agent=agent, user=user, title=title or agent.name, metadata=metadata or {}
    )


def append_message(
    conversation: AgentConversation,
    run: AgentRun | None,
    role: str,
    content: str,
    *,
    metadata: dict | None = None,
) -> AgentMessage:
    from .session import sanitize_message_text

    last = (
        AgentMessage.objects.filter(conversation=conversation)
        .order_by("-sequence")
        .values_list("sequence", flat=True)
        .first()
    )
    return AgentMessage.objects.create(
        conversation=conversation,
        run=run,
        role=role,
        content=sanitize_message_text(content),
        sequence=(last or 0) + 1,
        metadata=metadata or {},
    )


def create_run(
    conversation: AgentConversation,
    user_message: str,
    *,
    actor=None,
    mock_plan: list | None = None,
) -> tuple[AgentRun, AgentMessage]:
    """Synchronously-validated run creation.

    Returns the pending ``AgentRun`` + the persisted user ``AgentMessage``.
    Execution is dispatched by the caller (``tasks.schedule_agent_run``).
    Fails fast with ``AgentRegistryError`` so the API can 4xx before any
    work is scheduled.
    """
    agent = conversation.agent
    if agent is None:
        raise AgentRegistryError("agent_unbound")
    if agent.status != "active":
        raise AgentRegistryError("agent_not_active")

    audience = agent.audience
    if audience == "staff" and not _is_staff_or_admin(conversation.user):
        raise AgentRegistryError("agent_staff_only")
    if audience == "users" and not _is_authenticated(conversation.user):
        raise AgentRegistryError("agent_users_only")

    if agent.feature_id is not None and agent.feature is not None:
        from ai_intelligence.services import is_feature_available

        if not is_feature_available(agent.feature.feature_id, user=conversation.user):
            raise AgentRegistryError("feature_unavailable")

    run = AgentRun.objects.create(
        run_key=uuid.uuid4(),
        conversation=conversation,
        agent=agent,
        user=conversation.user,
        created_by=actor,
        status="pending",
        metadata={"mock_plan": mock_plan} if mock_plan else {},
    )
    message = append_message(conversation, run, "user", user_message)
    return run, message


def _is_staff_or_admin(user) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_staff", False) or getattr(user, "role", "") == "admin")


def _is_authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


# ---------------------------------------------------------------------------
# Proposal lifecycle
# ---------------------------------------------------------------------------


def create_proposal(
    run: AgentRun,
    tool,
    arguments: dict,
    tool_call_id: str,
    *,
    approval_required: str = "any_staff",
    actor=None,
) -> AgentProposal:
    """Create a PENDING proposal for a state-changing tool action + the
    associated AgentToolCall row. Called by the session."""

    from fraud.services.privacy import sanitize_dict

    title = f"{tool.name} — state-changing action"
    summary = (
        f"Agent run {run.run_key} requested tool {tool.name} with "
        f"{len(arguments)} argument(s); a human reviewer must approve before "
        f"it is applied."
    )
    ttl = getattr(settings, "AGENTS_PROPOSAL_TTL_SECONDS", 86400)

    with transaction.atomic():
        tool_call = AgentToolCall.objects.create(
            run=run,
            tool_name=tool.name,
            arguments=sanitize_dict(arguments),
            execution_status="proposed",
            permission_decision="proposed",
            actor=actor,
            result={},
        )
        proposal = AgentProposal.objects.create(
            proposal_key=uuid.uuid4(),
            run=run,
            tool_call=tool_call,
            proposal_type=tool.name,
            title=title,
            summary=summary,
            action={
                "tool": tool.name,
                "arguments": sanitize_dict(arguments),
                "tool_call_id": tool_call_id,
            },
            status=ProposalStatus.PENDING,
            approval_required=approval_required,
            created_by=actor,
            expires_at=timezone.now() + timezone.timedelta(seconds=ttl),
            meta={"tool_call_id": tool_call_id},
        )
    try:
        from audit.services import log_action

        log_action(
            actor=actor,
            action="agent.proposal.created",
            target=proposal,
            detail=f"proposal {proposal.proposal_key} for {tool.name}",
        )
    except Exception:
        pass
    return proposal


def _is_admin_role(reviewer) -> bool:
    """Strict admin check for HIGH_RISK proposals.

    ``config.trust_utils.is_admin_user`` treats any staff member as admin,
    but the admin-only proposal ceiling must be role-level (``role ==
    "admin"``) or a superuser, otherwise every staff reviewer could approve
    HIGH_RISK actions.
    """
    if reviewer is None:
        return False
    return bool(
        getattr(reviewer, "is_superuser", False) or getattr(reviewer, "role", "") == "admin"
    )


def _check_reviewer(proposal: AgentProposal, reviewer) -> None:
    """Enforce the proposal's approval-required ceiling.

    ``any_staff`` requires admin/staff access (``is_admin_user``); ``admin``
    requires the strict role-level admin (``_is_admin_role``).
    """
    from config.trust_utils import is_admin_user

    if proposal.approval_required == "admin":
        if not _is_admin_role(reviewer):
            raise ProposalError("admin_approval_required")
        return
    if not is_admin_user(reviewer):
        raise ProposalError("staff_reviewer_required")


@transaction.atomic
def approve_proposal(proposal: AgentProposal, reviewer, *, note: str = "") -> AgentProposal:
    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == ProposalStatus.APPLIED:
        raise ProposalError("already_applied")
    if locked.status == ProposalStatus.PENDING and locked.is_expired:
        # Expired proposals are marked by the expiring task, not here — this
        # atomic block would roll back any write on raise.
        raise ProposalError("expired")
    if locked.status != ProposalStatus.PENDING:
        raise ProposalError(f"cannot_approve_{locked.status}")

    _check_reviewer(locked, reviewer)
    locked.status = ProposalStatus.APPROVED
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = reviewer
    locked.meta = {**locked.meta, "approval_note": (note or "")[:500]}
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=reviewer,
            action="agent.proposal.approved",
            target=locked,
            detail=f"approved proposal {locked.proposal_key}",
        )
    except Exception:
        pass
    return locked


@transaction.atomic
def reject_proposal(proposal: AgentProposal, reviewer, *, reason: str = "") -> AgentProposal:
    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == ProposalStatus.APPLIED:
        raise ProposalError("already_applied")
    if locked.status != ProposalStatus.PENDING:
        raise ProposalError(f"cannot_reject_{locked.status}")

    _check_reviewer(locked, reviewer)
    locked.status = ProposalStatus.REJECTED
    locked.reviewed_at = timezone.now()
    locked.reviewed_by = reviewer
    locked.rejection_reason = (reason or "")[:2000]
    locked.meta = {**locked.meta, "reject_reason": (reason or "")[:500]}
    locked.save(update_fields=["status", "reviewed_at", "reviewed_by", "rejection_reason", "meta"])
    try:
        from audit.services import log_action

        log_action(
            actor=reviewer,
            action="agent.proposal.rejected",
            target=locked,
            detail=f"rejected proposal {locked.proposal_key}",
        )
    except Exception:
        pass
    return locked


@transaction.atomic
def apply_proposal(proposal: AgentProposal, *, actor=None) -> AgentProposal:
    """Apply an APPROVED proposal exactly once.

    Concurrency-safe (``select_for_update`` + status guard) and idempotent:
    applying an APPLIED proposal is a no-op that re-returns the stored result.
    Only the tool registry + JSON schema gate the applied action, so this is
    the authoritative enforcement point for human-approval guarantees (replay
    prevention: a proposal that was rejected/expired can never become
    actionable again).
    """
    locked = AgentProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status == ProposalStatus.APPLIED:
        # Idempotent replay guard — a no-op return (no writes), so the atomic
        # block has nothing to roll back: double-applies are safe to repeat.
        return locked
    if locked.status != ProposalStatus.APPROVED:
        raise ProposalError(f"proposal_not_approved ({locked.status})")
    if locked.is_expired:
        # Same as approve: expiry is recorded by the expiring task; this
        # atomic block would roll back any write on raise.
        raise ProposalError("expired")

    action = locked.action or {}
    tool = AgentToolRegistry.get(action.get("tool", ""))
    if tool is None:
        raise ProposalError(f"tool {action.get('tool', '')!r} is not registered")

    arguments = action.get("arguments") or {}
    try:
        tool.validate_arguments(arguments)
    except Exception as exc:
        raise ProposalError(f"proposal arguments invalid: {exc}") from exc

    context = {
        "actor": actor,
        "user": locked.run.user if locked.run else None,
        "agent": locked.run.agent if locked.run else None,
        "conversation": locked.run.conversation if locked.run else None,
        "proposal_key": locked.proposal_key,
    }
    outcome = tool.execute(arguments, context)

    locked.application_result = outcome
    locked.applied_at = timezone.now()
    locked.applied_by = actor
    locked.status = ProposalStatus.APPLIED if outcome.get(RESULT_OK) else ProposalStatus.FAILED
    locked.save(update_fields=["application_result", "applied_at", "applied_by", "status"])
    if locked.tool_call_id:
        AgentToolCall.objects.filter(pk=locked.tool_call_id).update(
            execution_status="executed" if outcome.get(RESULT_OK) else "failed",
            result=outcome,
            completed_at=timezone.now(),
        )
    try:
        from audit.services import log_action

        log_action(
            actor=actor,
            action="agent.proposal.applied",
            target=locked,
            detail=(f"applied proposal {locked.proposal_key} -> {locked.status}"),
        )
    except Exception:
        pass
    return locked


@transaction.atomic
def expire_proposals(*, dry_run: bool = False) -> int:
    """Expire PENDING (and APPROVED-but-unapplied) proposals past their
    deadline. Returns the count."""
    now = timezone.now()
    qs = AgentProposal.objects.filter(
        status__in=[ProposalStatus.PENDING, ProposalStatus.APPROVED],
        expires_at__lte=now,
    )
    if dry_run:
        return qs.count()
    count = 0
    for proposal in qs.select_for_update():
        proposal.status = ProposalStatus.EXPIRED
        proposal.save(update_fields=["status"])
        count += 1
    return count


# ---------------------------------------------------------------------------
# Evaluation hook + notifications
# ---------------------------------------------------------------------------


def create_agent_eval_run(
    run_id: int, *, feature_id: str = "", metric_keys: list[str] | None = None
):
    """Evaluation integration hook (Phase 18.3).

    Creates a PENDING ``EvaluationRun`` snapshot of a finished agent run so
    the platform can later evaluate the agent's behavior without rebuilding
    provenance. Deliberately does NOT execute any dataset or fabricate a score.
    """
    run = AgentRun.objects.filter(pk=run_id).first()
    if run is None:
        raise AgentRegistryError("run_not_found")

    from ai_intelligence.models import AIFeatureRegistry, AIPrompt, EvaluationRun

    feature = None
    prompt = None
    if feature_id:
        feature = AIFeatureRegistry.objects.filter(feature_id=feature_id).first()
    if run.prompt_key:
        prompt = AIPrompt.objects.filter(prompt_key=run.prompt_key).first()

    return EvaluationRun.objects.create(
        feature=feature,
        dataset=None,
        dataset_version=0,
        prompt=prompt,
        prompt_version=run.prompt_version,
        model_name=run.model_name,
        provider=run.provider,
        status="pending",
        experiment_key="agent-run",
        variant_key=str(run.run_key),
        metadata={
            "agent_run_id": run.pk,
            "agent_key": run.agent.key if run.agent else "",
            "metric_keys": metric_keys or [],
            "tool_sequence": run.metadata.get("tool_sequence", []),
        },
    )


def notify_run_outcome(run: AgentRun) -> None:
    """Surface meaningful agent-run outcomes through the platform
    notification + audit channels (Phase 18.4 ``ai_alert`` stream)."""
    if run.status not in ("failed", "terminated"):
        return
    user = run.conversation.user if run.conversation_id else None
    if user is None:
        return

    from notifications.utils import create_notification

    is_failure = run.status == "failed"
    title = "Agent run failed" if is_failure else "Agent run stopped (guardrail)"
    message = f"Agent {run.agent.key if run.agent else '?'} ended in {run.status}" + (
        f" — {run.termination_reason}" if run.termination_reason else ""
    )
    with suppress(Exception):  # notifications must never break run finalization
        create_notification(
            user,
            "ai_alert",
            title=title,
            message=message,
            action_url="",
            meta={
                "run_key": str(run.run_key),
                "status": run.status,
                "termination_reason": run.termination_reason,
            },
        )
    try:
        from audit.services import log_action

        log_action(
            actor=run.user if run.user_id else None,
            action="agent.run.outcome",
            target=run,
            detail=f"run {run.run_key} {run.status} ({run.termination_reason})",
        )
    except Exception:
        pass
