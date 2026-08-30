"""AgentSession — the guarded, telemetried agent turn loop — Phase 19.0.

Responsibilities:

* run the bounded turn loop inside a single ``AgentRun``
* resolve providers through the Phase 18 provider registry and route every
  model call through ``BaseProvider`` + ``TelemetryMixin`` (dashboard data
  is produced for free, and ``AIExecutionLog`` rows are enriched with the
  run's prompt attribution + estimated cost)
* resolve system prompts through the Phase 18.2 prompt registry (never
  hardcode real prompts)
* verify + JSON-schema-validate tool calls against the tool registry
* enforce the server-side permission model:

  * READ_ONLY      -> executed immediately (recorded + audited)
  * STATE_CHANGING -> proposal created, human approval required
  * HIGH_RISK      -> proposal created, admin-only approval required

* enforce guardrails: max turns, max tool calls, max tokens, max cost,
  wall-clock timeout, max consecutive tool failures
* persist only sanitized message text (PII/secret-safe), and keep every tool
  outcome server-grounded (TOOL-DERIVED), never model-invented.

The session is synchronous; async execution is hosted by ``tasks.py`` via a
plain shared task (no ``autoretry_for`` — an exception must not auto-reapply
side effects).
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import suppress
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from .errors import AgentSessionError
from .providers import MockAgentProvider, resolve_provider
from .tools import (
    HIGH_RISK,
    PERMISSION_CAPABILITIES,
    READ_ONLY,
    RESULT_OK,
    AgentToolRegistry,
    ToolValidationError,
    register_builtin_tools,
)

if TYPE_CHECKING:
    from .models import AgentRun

# Guardrail termination reasons.
G_MAX_TURNS = "max_turns_exceeded"
G_MAX_TOOL_CALLS = "max_tool_calls_exceeded"
G_MAX_TOKENS = "max_tokens_exceeded"
G_MAX_COST = "max_cost_exceeded"
G_TIMEOUT = "timeout"
G_CONSECUTIVE_FAILURES = "consecutive_tool_failures"

# Specific session-config failures map to their own termination reason so the
# ops surface can tell them apart from a generic "unavailable".
_SESSION_TERMINATION_REASONS = {
    "agent_not_active": "agent_not_active",
    "feature_unavailable": "feature_unavailable",
    "agent_unbound": "agent_unbound",
    "conversation_not_active": "conversation_not_active",
    "agent_staff_only": "agent_staff_only",
    "agent_users_only": "agent_users_only",
    "prompt_unavailable": "prompt_unavailable",
    "agent_has_no_prompt_configured": "agent_has_no_prompt_configured",
}


def sanitize_message_text(text, limit: int = 8000) -> str:
    """Strip control characters and cap length so transcripts stay clean."""
    cleaned = (text or "").replace("\x00", "").replace("\r", "")
    if len(cleaned) > limit:
        cleaned = cleaned[:limit]
    return cleaned


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


class AgentSession:
    def __init__(self, conversation, *, actor=None, request_id: str = ""):
        self.conversation = conversation
        self.agent = conversation.agent
        self.user = conversation.user
        self.actor = actor
        self.request_id = request_id
        self.context_window = getattr(settings, "AGENTS_CONTEXT_WINDOW_MESSAGES", 40)

    # ------------------------------------------------------------------ API

    def execute(self, run) -> AgentRun:
        """Run the bounded loop for ``run``. Never raises; the outcome is a
        finished ``AgentRun`` row (completed / terminated / failed)."""

        register_builtin_tools()

        started_ms = int(time.perf_counter() * 1000)
        run.started_at = timezone.now()
        run.status = "running"
        run.save(update_fields=["started_at", "status", "updated_at"])

        try:
            self._validate_run(run)
            provider, provider_reason = resolve_provider(
                self.agent.provider,
                feature_id=(
                    self.agent.feature.feature_id if self.agent.feature else "rentora.agent"
                ),
            )
            if provider is None:
                return self._finish_failed(
                    run, "provider_not_configured", provider_reason, started_ms
                )

            # Mock adapter is a TEST ADAPTER: refuse outside test/debug.
            if isinstance(provider, MockAgentProvider) and not self._mock_allowed():
                return self._finish_failed(
                    run,
                    "provider_not_configured",
                    "mock provider disabled in this environment",
                    started_ms,
                )

            system_prompt, prompt_key, prompt_version = self._build_system_prompt()
            run.prompt_key = prompt_key
            run.prompt_version = prompt_version
            run.provider = provider.name
            run.model_name = self.agent.model_name or (
                self.agent.feature.default_model if self.agent.feature else ""
            )

            tools_spec = [t.spec for t in self._allowed_tools()]
            messages = self._build_messages(system_prompt)

            plan = run.metadata.get("mock_plan")
            mock_plan_ref = list(plan) if plan else None

            self._loop(run, provider, messages, tools_spec, mock_plan_ref, started_ms)
        except AgentSessionError as exc:
            reason = _SESSION_TERMINATION_REASONS.get(
                str(exc).split(":")[0].strip(), "agent_unavailable"
            )
            self._finish_failed(run, reason, str(exc), started_ms)
        except Exception as exc:
            self._finish_failed(run, "internal_error", f"{type(exc).__name__}: {exc}", started_ms)
        finally:
            self._finalize(run, started_ms)
        return run

    # --------------------------------------------------------------- guards

    def _mock_allowed(self) -> bool:
        return getattr(settings, "AGENTS_DEBUG_TOOLS", False) or settings.ENVIRONMENT == "test"

    def _validate_run(self, run) -> None:
        if self.conversation.status != "active":
            raise AgentSessionError("conversation_not_active")
        if self.agent is None:
            raise AgentSessionError("agent_unbound")
        if self.agent.status != "active":
            raise AgentSessionError("agent_not_active")
        audience = self.agent.audience
        if audience == "staff" and not self._is_staff_or_admin(self.user):
            raise AgentSessionError("agent_staff_only")
        if audience == "users" and not self._is_authenticated(self.user):
            raise AgentSessionError("agent_users_only")
        if self.agent.feature is not None:
            from ai_intelligence.services import is_feature_available

            if not is_feature_available(self.agent.feature.feature_id, user=self.user):
                raise AgentSessionError("feature_unavailable")

    @staticmethod
    def _is_staff_or_admin(user) -> bool:
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return bool(getattr(user, "is_staff", False) or getattr(user, "role", "") == "admin")

    @staticmethod
    def _is_authenticated(user) -> bool:
        return bool(user is not None and getattr(user, "is_authenticated", False))

    def _allowed_tools(self):
        tools = [t for t in AgentToolRegistry.all() if t.enabled]
        allowlist = self.agent.enabled_tools or []
        if allowlist:
            tools = [t for t in tools if t.name in allowlist]
        return tools

    # -------------------------------------------------------- prompt setup

    def _build_system_prompt(self):
        prompt_key = self.agent.prompt_key or ""
        rendered = ""
        version = 0
        instructions = self.agent.system_instructions or ""
        if prompt_key:
            from ai_intelligence.services import render_prompt

            context = {
                "agent_key": self.agent.key,
                "agent_name": self.agent.name,
                "agent_description": self.agent.description,
                "conversation_id": str(self.conversation.pk),
            }
            try:
                rendered = render_prompt(prompt_key, context)
            except DjangoValidationError:
                # No active prompt version yet — fall back to the agent's
                # inline instructions so the agent can still run.
                if not instructions:
                    raise AgentSessionError("prompt_unavailable") from None
                prompt_key = ""
            version = self.active_prompt_version(prompt_key)

        system_text = "\n\n".join(part for part in (rendered, instructions) if part)
        if not system_text:
            raise AgentSessionError("agent_has_no_prompt_configured")
        return sanitize_message_text(system_text, limit=12000), prompt_key, version

    @staticmethod
    def active_prompt_version(prompt_key: str) -> int:
        from ai_intelligence.models import AIPromptVersion

        version = (
            AIPromptVersion.objects.filter(prompt__prompt_key=prompt_key, is_active=True)
            .order_by("-version")
            .first()
        )
        return version.version if version else 0

    # -------------------------------------------------------------- messages

    def _build_messages(self, system_prompt: str):
        """Rebuild the OpenAI wire format from the durable transcript.

        Tool turns stay server-grounded: assistant ``tool_calls`` frames and
        their ``tool`` results are reconstructed from the persisted assistant
        message metadata + the tool outcome rows — never from the model's
        claims.
        """
        from .models import AgentMessage

        msgs = list(
            AgentMessage.objects.filter(conversation=self.conversation).order_by("sequence")
        )[-self.context_window :]

        wire: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in msgs:
            extra = msg.metadata or {}
            if msg.role == "system":
                continue
            if msg.role == "user":
                wire.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                if extra.get("tool_call"):
                    tc = extra["tool_call"]
                    wire.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [
                                {
                                    "id": extra.get("tool_call_id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": tc.get("name", ""),
                                        "arguments": _json_dumps(tc.get("arguments", {})),
                                    },
                                }
                            ],
                        }
                    )
                else:
                    wire.append({"role": "assistant", "content": msg.content})
            elif msg.role == "tool":
                wire.append(
                    {
                        "role": "tool",
                        "tool_call_id": extra.get("tool_call_id", ""),
                        "content": msg.content,
                    }
                )
        # A trailing assistant tool_calls frame with no tool result would be
        # an invalid protocol — drop it defensively.
        if wire and wire[-1]["role"] == "assistant" and "tool_calls" in wire[-1]:
            wire[-1] = {"role": "assistant", "content": wire[-1]["content"]}
        return wire

    # ----------------------------------------------------------------- loop

    def _loop(self, run, provider, messages, tools_spec, mock_plan_ref, started_ms):
        from fraud.services.privacy import sanitize_reason

        total_input = 0
        total_output = 0
        total_cost = Decimal("0")
        consecutive_failures = 0
        tool_call_count = 0
        turn_count = 0
        tool_sequence: list[dict] = []

        while True:
            reason = self._guardrail_reason(
                turn_count,
                tool_call_count,
                consecutive_failures,
                total_input + total_output,
                total_cost,
                started_ms,
            )
            if reason is not None:
                self._apply_totals(
                    run,
                    total_input,
                    total_output,
                    total_cost,
                    turn_count,
                    tool_call_count,
                    consecutive_failures,
                )
                self._persist_message(
                    run,
                    "assistant",
                    "I stopped because " + reason.replace("_", " ") + ".",
                    None,
                )
                return self._finish_terminated(run, reason, started_ms)

            turn_count += 1
            kwargs: dict = {
                "messages": messages,
                "tools": tools_spec,
                "model": run.model_name or None,
                "prompt_key": run.prompt_key,
                "prompt_version": run.prompt_version,
                "user": self.user,
                "request_id": self.request_id or str(run.run_key)[:12],
            }
            if mock_plan_ref is not None:
                kwargs["mock_plan"] = mock_plan_ref

            result = provider.run(**kwargs)

            incremental = self._incremental_cost(result, provider, run)
            total_input += result.input_tokens
            total_output += result.output_tokens
            total_cost += incremental
            self._enrich_telemetry(result, run, incremental)

            if not result.success:
                self._apply_totals(
                    run,
                    total_input,
                    total_output,
                    total_cost,
                    turn_count,
                    tool_call_count,
                    consecutive_failures,
                )
                run.error_message = sanitize_reason(result.reason or "provider failure")
                return self._finish_failed(run, "provider_failure", run.error_message, started_ms)

            data = result.data or {}
            kind = data.get("type")

            if kind == "text":
                text = sanitize_message_text(str(data.get("content", "")))
                self._persist_message(run, "assistant", text, None)
                run.status = "completed"
                run.termination_reason = ""
                break

            if kind == "pass":
                # Metadata-only turn (tokens/cost), no model output.
                continue

            if kind == "tool_call":
                tool_name = str(data.get("name", ""))
                arguments = data.get("arguments") or {}
                tool_call_id = str(data.get("id", f"call_{uuid.uuid4().hex[:8]}"))

                tool, verdict, failure = self._plan_tool_call(tool_name, arguments, run)
                tool_sequence.append({"name": tool_name, "verdict": verdict})
                run.metadata["tool_sequence"] = tool_sequence

                if verdict == "denied":
                    consecutive_failures += 1
                    payload = _json_dumps({"ok": False, "error": failure})
                    self._persist_tool_call_frame(run, tool_call_id, tool_name, arguments)
                    self._persist_message(
                        run, "tool", payload, {"tool_call_id": tool_call_id}, limit=200_000
                    )
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": _json_dumps(arguments),
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "tool_call_id": tool_call_id, "content": payload},
                        ]
                    )
                    continue

                if verdict == "read_allowed":
                    tool_call_count += 1
                    outcome = self._record_read_call(run, tool, tool_call_id, arguments)
                    if outcome.get(RESULT_OK):
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                    payload = _json_dumps(self._sanitized_outcome(outcome))
                    self._persist_tool_call_frame(run, tool_call_id, tool.name, arguments)
                    self._persist_message(
                        run, "tool", payload, {"tool_call_id": tool_call_id}, limit=200_000
                    )
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": tool_call_id,
                                        "type": "function",
                                        "function": {
                                            "name": tool.name,
                                            "arguments": _json_dumps(arguments),
                                        },
                                    }
                                ],
                            },
                            {"role": "tool", "tool_call_id": tool_call_id, "content": payload},
                        ]
                    )
                    continue

                # proposal path (state-changing / high-risk) — applied only by
                # a human reviewer through services.apply_proposal.
                tool_call_count += 1
                proposal = self._create_proposal(run, tool, tool_call_id, arguments)
                self._persist_tool_call_frame(run, tool_call_id, tool.name, arguments)
                payload = _json_dumps(
                    {
                        "proposal_created": True,
                        "proposal_key": str(proposal.proposal_key),
                        "summary": proposal.summary[:400],
                        "status": proposal.status,
                        "pending_approval": True,
                    }
                )
                self._persist_message(
                    run, "tool", payload, {"tool_call_id": tool_call_id}, limit=200_000
                )
                messages.extend(
                    [
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool.name,
                                        "arguments": _json_dumps(arguments),
                                    },
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": tool_call_id, "content": payload},
                    ]
                )
                continue

            # Unknown response kind -> treat as a tool failure and keep going
            # (bounded by the consecutive-failure guardrail).
            consecutive_failures += 1
            self._persist_message(
                run,
                "tool",
                _json_dumps({"ok": False, "error": f"unknown model response: {kind}"}),
                None,
            )

        # Text-complete path — persist run-scoped totals.
        self._apply_totals(
            run,
            total_input,
            total_output,
            total_cost,
            turn_count,
            tool_call_count,
            consecutive_failures,
        )

    def _apply_totals(
        self,
        run,
        total_input,
        total_output,
        total_cost,
        turn_count,
        tool_call_count,
        consecutive_failures,
    ):
        run.input_tokens = total_input
        run.output_tokens = total_output
        run.total_tokens = total_input + total_output
        run.estimated_cost_usd = total_cost
        run.turn_count = turn_count
        run.tool_call_count = tool_call_count
        run.consecutive_tool_failures = consecutive_failures

    def _guardrail_reason(
        self, turns, tool_calls, failures, tokens, cost, started_ms
    ) -> str | None:
        limits = self._limits()
        if turns >= limits["max_turns"]:
            return G_MAX_TURNS
        if tool_calls >= limits["max_tool_calls"]:
            return G_MAX_TOOL_CALLS
        if tokens >= limits["max_tokens"]:
            return G_MAX_TOKENS
        if cost >= limits["max_cost_usd"]:
            return G_MAX_COST
        elapsed_ms = int(time.perf_counter() * 1000) - started_ms
        if elapsed_ms >= limits["timeout_seconds"] * 1000:
            return G_TIMEOUT
        if failures >= getattr(settings, "AGENTS_MAX_CONSECUTIVE_TOOL_FAILURES", 3):
            return G_CONSECUTIVE_FAILURES
        return None

    def _limits(self):
        return {
            "max_turns": self.agent.turn_limit,
            "max_tool_calls": self.agent.tool_limit,
            "max_tokens": self.agent.token_limit,
            "max_cost_usd": self.agent.cost_limit_usd,
            "timeout_seconds": self.agent.timeout_seconds_value,
        }

    def _incremental_cost(self, result, provider, run) -> Decimal:
        """Exact provider-reported cost (when available) else estimation."""
        metadata = result.metadata or {}
        reported = metadata.get("cost_usd")
        if reported is not None:
            try:
                cost = Decimal(str(reported))
                if cost > Decimal("0"):
                    return cost
            except Exception:
                pass
        return self._cost(provider.name, run.model_name, result.input_tokens, result.output_tokens)

    def _cost(self, provider_name, model_name, in_tokens, out_tokens):
        from ai_intelligence.services import calculate_estimated_cost

        try:
            return calculate_estimated_cost(
                provider_name, model_name or "", in_tokens or 0, out_tokens or 0
            )
        except Exception:
            return Decimal("0")

    def _enrich_telemetry(self, result, run, incremental_cost: Decimal | None = None):
        """Attach prompt attribution + incremental cost to the platform log."""
        execution_id = (result.metadata or {}).get("execution_id")
        if not execution_id:
            return
        try:
            from ai_intelligence.models import AIExecutionLog

            prior = AIExecutionLog.objects.filter(execution_id=execution_id).values_list(
                "estimated_cost_usd", flat=True
            ).first() or Decimal("0")
            if incremental_cost is None:
                incremental_cost = self._cost(
                    run.provider, run.model_name, result.input_tokens, result.output_tokens
                )
            AIExecutionLog.objects.filter(execution_id=execution_id).update(
                prompt_key=run.prompt_key or "",
                prompt_version=run.prompt_version or 0,
                estimated_cost_usd=Decimal(prior) + incremental_cost,
            )
        except Exception:
            pass

    # ------------------------------------------------------------ tool plan

    def _plan_tool_call(self, tool_name, arguments, run):
        """Server-side tool planning — the authoritative permission layer.

        Returns ``(tool, verdict, message)`` where verdict is one of
        ``denied`` / ``read_allowed`` / ``proposed``.
        """
        tool = AgentToolRegistry.get(tool_name)
        if tool is None:
            return None, "denied", f"tool {tool_name!r} is not registered"

        allowed_caps = PERMISSION_CAPABILITIES.get(self.agent.permission, set())
        if tool.capability not in allowed_caps:
            return tool, "denied", f"tool {tool_name!r} requires capability {tool.capability}"

        allowlist = self.agent.enabled_tools or []
        if allowlist and tool_name not in allowlist:
            return tool, "denied", f"tool {tool_name!r} is not in the agent's allowlist"

        try:
            tool.validate_arguments(arguments)
        except ToolValidationError as exc:
            return tool, "denied", str(exc)

        if tool.capability == READ_ONLY:
            return tool, "read_allowed", "ok"
        if tool.capability == HIGH_RISK:
            return tool, "proposed", "admin_approval"
        return tool, "proposed", "state_change"

    def _tool_context(self):
        return {
            "actor": self.actor,
            "user": self.user,
            "agent": self.agent,
            "conversation": self.conversation,
            "request_id": self.request_id,
        }

    def _record_read_call(self, run, tool, tool_call_id, arguments):
        """Execute a READ_ONLY tool, persist the audited AgentToolCall row and
        return the sanitized outcome envelope."""
        from audit.services import log_action
        from fraud.services.privacy import sanitize_dict

        from .models import AgentToolCall

        started = int(time.perf_counter() * 1000)
        outcome = self._sanitized_outcome(tool.execute(arguments, self._tool_context()))
        AgentToolCall.objects.create(
            run=run,
            tool_name=tool.name,
            arguments=sanitize_dict(arguments),
            execution_status="executed" if outcome.get(RESULT_OK) else "failed",
            permission_decision="read_allowed",
            result=outcome,
            error_message=(outcome.get("error") or "")[:500],
            actor=self.actor,
            duration_ms=max(1, int(time.perf_counter() * 1000) - started),
        )
        if tool.audit:
            with suppress(Exception):  # audit must never break the tool call
                log_action(
                    actor=self.actor,
                    action=f"agent.tool.{tool.name}",
                    target=run,
                    detail=f"read tool {tool.name} for run {run.run_key}",
                )
        return outcome

    def _persist_tool_call_frame(self, run, tool_call_id, tool_name, arguments):
        """Assistant-side tool_calls frame so the wire protocol stays valid
        (assistant frame always precedes its tool result)."""
        from fraud.services.privacy import sanitize_dict

        self._persist_message(
            run,
            "assistant",
            "",
            {
                "tool_call_id": tool_call_id,
                "tool_call": {"name": tool_name, "arguments": sanitize_dict(arguments)},
            },
        )

    def _create_proposal(self, run, tool, tool_call_id, arguments):
        from .services import create_proposal

        approval = "admin" if tool.capability == HIGH_RISK else "any_staff"
        return create_proposal(
            run=run,
            tool=tool,
            arguments=arguments,
            tool_call_id=tool_call_id,
            approval_required=approval,
            actor=self.actor,
        )

    # ---------------------------------------------------------------- finish

    def _sanitized_outcome(self, outcome, _depth=0):
        """Mask sensitive fields and bound depth/size for JSON storage.

        Outcome payloads come from tool executors (and potentially future
        LLM-echoed data) — mask sensitive keys at every level, truncate long
        strings, and never store an unbounded structure in
        ``AgentToolCall.result``. Depth is bounded deep enough that a
        structured tool envelope (``ok -> data -> list -> row -> fields``)
        survives intact — deep rows must not be nulled out, or the LLM (and
        any consumer) loses the grounded facts those rows carry.
        """
        from fraud.services.privacy import mask_value

        if _depth >= 8:
            return None
        if isinstance(outcome, dict):
            return {
                k: self._sanitized_outcome(mask_value(k, v), _depth + 1)
                for k, v in list(outcome.items())[:200]
            }
        if isinstance(outcome, (list, tuple)):
            return [self._sanitized_outcome(v, _depth + 1) for v in list(outcome)[:200]]
        if isinstance(outcome, str):
            return outcome[:2000]
        if isinstance(outcome, (bool, int, float)) or outcome is None:
            return outcome
        return str(outcome)[:2000]

    def _persist_message(self, run, role, content, metadata, *, limit: int = 8000):
        from .models import AgentMessage

        last = (
            AgentMessage.objects.filter(conversation=self.conversation)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        )
        AgentMessage.objects.create(
            conversation=self.conversation,
            run=run,
            role=role,
            content=sanitize_message_text(content, limit=limit)
            if isinstance(content, str)
            else content,
            sequence=(last or 0) + 1,
            metadata=metadata or {},
        )

    def _finish_failed(self, run, reason, message, started_ms):
        run.status = "failed"
        run.termination_reason = reason
        run.error_message = (message or "")[:4000]
        return run

    def _finish_terminated(self, run, reason, started_ms):
        run.status = "terminated"
        run.termination_reason = reason
        return run

    def _finalize(self, run, started_ms):
        from .models import AgentRun
        from .services import notify_run_outcome

        now = timezone.now()
        run.completed_at = now
        run.duration_ms = max(0, int(time.perf_counter() * 1000) - started_ms)
        with suppress(Exception):  # the session must never raise in cleanup
            AgentRun.objects.filter(pk=run.pk).update(
                status=run.status,
                termination_reason=run.termination_reason[:100],
                error_message=run.error_message[:4000],
                completed_at=now,
                duration_ms=run.duration_ms,
                provider=run.provider[:100],
                model_name=run.model_name[:200],
                prompt_key=run.prompt_key[:100],
                prompt_version=run.prompt_version,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                total_tokens=run.total_tokens,
                turn_count=run.turn_count,
                tool_call_count=run.tool_call_count,
                consecutive_tool_failures=run.consecutive_tool_failures,
                estimated_cost_usd=run.estimated_cost_usd,
                metadata=run.metadata,
            )
        with suppress(Exception):
            self.conversation.last_activity_at = now
            self.conversation.save(update_fields=["last_activity_at"])
        with suppress(Exception):
            notify_run_outcome(run)
