"""Agent SDK data model — Phase 19.0.

Agent registry, conversations, messages, runs, audited tool calls, and the
human-review proposal lifecycle built on top of the Phase 18 foundation
(provider registry, telemetry, prompt registry, feature flags, evaluation).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AgentStatus(models.TextChoices):
    """Lifecycle of an agent definition. Default is ``disabled`` (safe)."""

    DRAFT = "draft", _("Draft")
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")
    DISABLED = "disabled", _("Disabled")


class AgentAudience(models.TextChoices):
    """Who may invoke an agent.

    The default is ``staff`` — no autonomous self-serve agent is available
    until an operator deliberately widens access.
    """

    STAFF = "staff", _("Staff only")
    USERS = "users", _("Authenticated users")
    PUBLIC = "public", _("Public")


class AgentPermission(models.TextChoices):
    """Capability ceiling the agent runs under (defense in depth — the server
    also enforces per-tool permissions; this is the agent-level ceiling).
    """

    VIEWER = "viewer", _("Read-only")
    OPERATOR = "operator", _("Operator (can execute state-changing tools)")
    ADMIN = "admin", _("Admin (higher-risk tools allowed)")


class ConversationStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")
    CLOSED = "closed", _("Closed")


class MessageRole(models.TextChoices):
    SYSTEM = "system", _("System")
    USER = "user", _("User")
    ASSISTANT = "assistant", _("Assistant")
    TOOL = "tool", _("Tool")


class RunStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    COMPLETED = "completed", _("Completed")
    TERMINATED = "terminated", _("Terminated (guardrail)")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class ToolCallStatus(models.TextChoices):
    REQUESTED = "requested", _("Requested")
    EXECUTED = "executed", _("Executed")
    PROPOSED = "proposed", _("Proposed for review")
    DENIED = "denied", _("Denied")
    FAILED = "failed", _("Failed")


class PermissionDecision(models.TextChoices):
    """Server-side verdict for a requested tool call."""

    READ_ALLOWED = "read_allowed", _("Read allowed — executed")
    PROPOSED = "proposed", _("State-changing — proposal created")
    DENIED = "denied", _("Denied")


class ProposalStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    EXPIRED = "expired", _("Expired")
    APPLIED = "applied", _("Applied")
    FAILED = "failed", _("Apply failed")


class ProposalApproval(models.TextChoices):
    """Minimum reviewer role required to approve a proposal."""

    ANY_STAFF = "any_staff", _("Any staff member")
    ADMIN = "admin", _("Admin only")


class Agent(models.Model):
    """A registered, configurable AI agent definition."""

    key = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=AgentStatus.choices, default=AgentStatus.DISABLED
    )
    audience = models.CharField(
        max_length=16, choices=AgentAudience.choices, default=AgentAudience.STAFF
    )
    permission = models.CharField(
        max_length=16,
        choices=AgentPermission.choices,
        default=AgentPermission.OPERATOR,
        help_text=_(
            "Agent-level capability ceiling; per-tool server-side permissions still apply."
        ),
    )
    version = models.PositiveIntegerField(default=1)

    # Phase 18 integration — feature flag gating + telemetry attribution.
    feature = models.ForeignKey(
        "ai_intelligence.AIFeatureRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents",
        help_text=_("Linked AI feature (feature-flag gating + telemetry)."),
    )
    prompt_key = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Active-prompt key from the Phase 18.2 prompt registry."),
    )
    # Provider selection. Empty means "resolve from AI_AGENT_LLM_PROVIDER /
    # feature defaults"; otherwise names a registered provider (e.g. llm,
    # mock_llm). A provider that is not registered fails the run safely.
    provider = models.CharField(max_length=100, blank=True, default="")
    model_name = models.CharField(max_length=200, blank=True, default="")
    system_instructions = models.TextField(blank=True, default="")

    # Tool allowlist (keys). Empty = default allowlist for the agent's
    # permission tier. Non-empty = only these tool names may run.
    enabled_tools = models.JSONField(default=list, blank=True)
    # Optional per-agent overrides (None = derived from AGENTS_DEFAULT_*).
    max_turns = models.PositiveIntegerField(null=True, blank=True)
    max_tool_calls = models.PositiveIntegerField(null=True, blank=True)
    max_tokens = models.PositiveIntegerField(null=True, blank=True)
    max_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    timeout_seconds = models.PositiveIntegerField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name = _("Agent")
        verbose_name_plural = _("Agents")

    def __str__(self):
        return f"{self.key} ({self.status})"

    def clean(self):
        super().clean()
        if self.permission not in AgentPermission.values:
            raise ValidationError({"permission": _("Invalid permission.")})
        if self.audience not in AgentAudience.values:
            raise ValidationError({"audience": _("Invalid audience.")})

    @property
    def tool_limit(self) -> int:
        """Maximum tool calls per run (agent override or default)."""
        if self.max_tool_calls:
            return self.max_tool_calls
        return getattr(settings, "AGENTS_DEFAULT_MAX_TOOL_CALLS", 20)

    @property
    def turn_limit(self) -> int:
        if self.max_turns:
            return self.max_turns
        return getattr(settings, "AGENTS_DEFAULT_MAX_TURNS", 6)

    @property
    def token_limit(self) -> int:
        if self.max_tokens:
            return self.max_tokens
        return getattr(settings, "AGENTS_DEFAULT_MAX_TOKENS", 4000)

    @property
    def cost_limit_usd(self) -> Decimal:
        if self.max_cost_usd is not None:
            return self.max_cost_usd
        return Decimal(str(getattr(settings, "AGENTS_DEFAULT_MAX_COST_USD", "2.0")))

    @property
    def timeout_seconds_value(self) -> int:
        if self.timeout_seconds:
            return self.timeout_seconds
        return getattr(settings, "AGENTS_DEFAULT_TIMEOUT_SECONDS", 180)

    @property
    def is_invocable(self) -> bool:
        """An agent is invocable only when active. Feature availability is
        checked separately at run time (feature flags)."""
        return self.status == AgentStatus.ACTIVE


class AgentConversation(models.Model):
    """A user↔agent thread. Conversations are the durable unit of memory."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="conversations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_conversations",
    )
    title = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = _("Agent conversation")
        verbose_name_plural = _("Agent conversations")

    def __str__(self):
        return f"conv #{self.pk} → {self.agent_id}"


class AgentMessage(models.Model):
    """One persisted, sanitized turn in a conversation."""

    conversation = models.ForeignKey(
        AgentConversation, on_delete=models.CASCADE, related_name="messages"
    )
    run = models.ForeignKey(
        "AgentRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField(blank=True, default="")
    sequence = models.PositiveIntegerField(default=0)
    tool_call = models.ForeignKey(
        "AgentToolCall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sequence"],
                name="uniq_message_sequence_per_conversation",
            )
        ]
        verbose_name = _("Agent message")

    def __str__(self):
        return f"msg#{self.sequence} {self.role}"

    @property
    def next_sequence(self) -> int:
        return self.sequence  # convenience; stored message already has it


class AgentRun(models.Model):
    """One agentic execution (a bounded turn loop)."""

    run_key = models.UUIDField(unique=True, db_index=True)
    conversation = models.ForeignKey(
        AgentConversation, on_delete=models.CASCADE, related_name="runs"
    )
    agent = models.ForeignKey(
        Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name="runs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_runs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(max_length=16, choices=RunStatus.choices, default=RunStatus.PENDING)
    termination_reason = models.CharField(max_length=100, blank=True, default="")

    provider = models.CharField(max_length=100, blank=True, default="")
    model_name = models.CharField(max_length=200, blank=True, default="")
    prompt_key = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.PositiveIntegerField(default=0)

    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal("0"))
    turn_count = models.PositiveIntegerField(default=0)
    tool_call_count = models.PositiveIntegerField(default=0)
    consecutive_tool_failures = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    error_message = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["conversation", "created_at"]),
        ]
        verbose_name = _("Agent run")

    def __str__(self):
        return f"run {self.run_key} ({self.status})"


class AgentToolCall(models.Model):
    """A fully audited tool invocation: request → verdict → result."""

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="tool_calls")
    tool_name = models.CharField(max_length=100, db_index=True)
    arguments = models.JSONField(default=dict, blank=True)
    execution_status = models.CharField(
        max_length=16, choices=ToolCallStatus.choices, default=ToolCallStatus.REQUESTED
    )
    permission_decision = models.CharField(
        max_length=16,
        choices=PermissionDecision.choices,
        default=PermissionDecision.DENIED,
    )
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["run", "tool_name"]),
            models.Index(fields=["tool_name", "created_at"]),
        ]
        verbose_name = _("Agent tool call")

    def __str__(self):
        return f"{self.tool_name} → {self.permission_decision} ({self.execution_status})"


class AgentProposal(models.Model):
    """Human-review gate for state-changing tool actions.

    Lifecycle: PENDING → APPROVED/REJECTED/EXPIRED → APPLIED/FAILED.
    Only an APPROVED proposal can ever be applied, exactly once
    (select_for_update + status guard + keyed application stamp).
    """

    proposal_key = models.UUIDField(unique=True, db_index=True)
    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="proposals")
    tool_call = models.OneToOneField(
        AgentToolCall,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal",
    )
    proposal_type = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=200, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    action = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ProposalStatus.choices,
        default=ProposalStatus.PENDING,
    )
    approval_required = models.CharField(
        max_length=16,
        choices=ProposalApproval.choices,
        default=ProposalApproval.ANY_STAFF,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    rejection_reason = models.TextField(blank=True, default="")

    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    application_result = models.JSONField(default=dict, blank=True)

    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]
        verbose_name = _("Agent proposal")

    def __str__(self):
        return f"proposal {self.proposal_key} ({self.status})"

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at
