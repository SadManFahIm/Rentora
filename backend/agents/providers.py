"""Agent providers — Phase 19.0.

Every model call in the agents app goes through the Phase 18 provider
contract (``BaseProvider`` + ``TelemetryMixin``) so telemetry lands in the
18.4 dashboards for free. Two providers are registered under feature
``rentora.agent``:

* ``llm`` — ChatCompletions over ``requests`` to an OpenAI-compatible
  endpoint (no vendor SDK dependency). Used in production.
* ``mock_llm`` — deterministic scripted provider (``mock_plan`` kwarg) used
  by the test suite and local bring-up. It is a TEST ADAPTER: without a real
  provider configured, agent runs terminate with ``provider_not_configured``
  instead of silently inventing answers.

Registration is idempotent (the registry keeps the last class per name), so
module import time is safe.
"""

import json
import logging
import os
import uuid
from typing import Any

from django.conf import settings

from fraud.services.provider_base import (
    BaseProvider,
    FailureType,
    ProviderFailure,
    ProviderResult,
    Registry,
    TelemetryMixin,
)

logger = logging.getLogger(__name__)

# --- telemetry / prompt attribution ----------------------------------------
FEATURE_KEY = "rentora.agent"

# Name -> provider class, kept in sync with Registry.register below. Used for
# by-name resolution (agent.provider) that the Registry's setting-driven API
# does not offer.
_PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {}


# --- OpenAI-compatible chat completions ------------------------------------


class ChatLlmProvider(TelemetryMixin, BaseProvider):
    """Chat-completions provider over an OpenAI-compatible HTTP endpoint.

    Kwargs::

        provider.run(
            messages=[{"role": "system", "content": "..."}, ...],
            tools=[{"type": "function", "function": {...}}, ...],
            model="my-model",
            prompt_key="...", prompt_version=1,   # telemetry attribution
            user=request.user, request_id="...",  # handled by TelemetryMixin
        )
    """

    name = "llm"
    feature_id = FEATURE_KEY

    def _run(self, **kwargs: Any) -> ProviderResult:
        api_base = (getattr(settings, "AGENTS_LLM_API_BASE", "") or "").strip()
        api_key = getattr(settings, "AGENTS_LLM_API_KEY", "") or env_key()
        if not api_base or not api_key:
            raise ProviderFailure(
                "LLM provider not configured (AGENTS_LLM_API_BASE/API_KEY). "
                "Set AI_AGENT_LLM_PROVIDER=llm and configure the endpoint.",
                FailureType.SYSTEM_FAILURE,
            )

        import requests

        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools") or []
        model = kwargs.get("model") or getattr(settings, "AGENTS_LLM_MODEL", "") or "gpt-4o-mini"
        timeout = getattr(settings, "AGENTS_LLM_TIMEOUT_SECONDS", 30)

        payload: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")

        url = api_base.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            raise ProviderFailure(
                f"LLM endpoint unreachable: {type(exc).__name__}",
                FailureType.PROVIDER_FAILURE,
            ) from exc

        if resp.status_code != 200:
            # Never echo the response body verbatim — it may carry prompt
            # data or secrets. Truncate harshly.
            snippet = (resp.text or "")[:120].replace("\n", " ")
            raise ProviderFailure(
                f"LLM endpoint error HTTP {resp.status_code}: {snippet}",
                FailureType.PROVIDER_FAILURE,
            )

        try:
            data = resp.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage", {}) or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderFailure(
                f"LLM response malformed: {type(exc).__name__}",
                FailureType.PROVIDER_FAILURE,
            ) from exc

        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            call = tool_calls[0]
            raw_args = call.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args)
            except ValueError:
                arguments = {"_parse_error": raw_args[:200]}
            data_out = {
                "type": "tool_call",
                "id": call.get("id", f"llm_{uuid.uuid4().hex[:8]}"),
                "name": call.get("function", {}).get("name", ""),
                "arguments": arguments,
            }
        else:
            data_out = {
                "type": "text",
                "content": message.get("content") or "",
            }

        return ProviderResult.ok(
            self.name,
            data=data_out,
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata={
                "prompt_key": kwargs.get("prompt_key", ""),
                "prompt_version": kwargs.get("prompt_version", 0),
            },
        )


class MockAgentProvider(TelemetryMixin, BaseProvider):
    """Deterministic scripted provider for tests / local bring-up.

    The session passes the whole remaining ``mock_plan`` list each turn; each
    invocation pops the next step so callers keep turn state naturally.

    Step forms::

        {"type": "text", "content": "..."}              # final assistant text
        {"type": "tool_call", "name": "...", "arguments": {...}}
        {"type": "pass"}                                # metadata-only turn
        {"type": "usage", "input_tokens": N, "output_tokens": M,
         "cost_usd": optional}                          # metadata turn (pass)
        {"type": "error", "reason": "..."}              # -> ProviderFailure
        {"type": "raise"}                               # -> unexpected error

    ``usage``/``pass`` turns carry tokens/cost without producing model output
    so guardrails can be exercised against real accumulation. If the plan
    runs out, a final ``done`` text is emitted to end the loop.
    """

    name = "mock_llm"
    feature_id = FEATURE_KEY

    def _run(self, **kwargs: Any) -> ProviderResult:
        plan = kwargs.get("mock_plan") or []
        step = plan.pop(0) if plan else {"type": "done"}
        step_type = step.get("type", "done")

        if step_type == "raise":
            raise RuntimeError("mock provider boom")
        if step_type == "error":
            raise ProviderFailure(step.get("reason", "mock failure"), FailureType.PROVIDER_FAILURE)

        input_tokens = int(step.get("input_tokens") or 0)
        output_tokens = int(step.get("output_tokens") or 0)
        metadata: dict[str, Any] = {
            "mock": True,
            "prompt_key": kwargs.get("prompt_key", ""),
            "prompt_version": kwargs.get("prompt_version", 0),
        }
        # The test adapter may report an exact cost so guardrails like
        # max_cost can be exercised deterministically (the production
        # ChatLlmProvider relies on cost estimation instead).
        if step.get("cost_usd") is not None:
            metadata["cost_usd"] = str(step["cost_usd"])

        if step_type == "tool_call":
            name = step.get("name", "")
            tool_id = step.get("id", f"mock_{uuid.uuid4().hex[:8]}")
            data = {
                "type": "tool_call",
                "id": tool_id,
                "name": name,
                "arguments": step.get("arguments") or {},
            }
        elif step_type in ("text", "done"):
            data = {
                "type": "text",
                "content": step.get("content") or "Understood.",
            }
        else:
            data = {"type": "pass"}

        return ProviderResult.ok(
            self.name,
            data=data,
            model_name=kwargs.get("model") or "mock-1",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata=metadata,
        )


def env_key() -> str:
    return os.getenv("AGENTS_LLM_API_KEY", "")


def register_agent_providers() -> None:
    """Idempotent registration under the ``rentora.agent`` feature."""
    Registry.register(FEATURE_KEY, "llm", ChatLlmProvider)
    Registry.register(FEATURE_KEY, "mock_llm", MockAgentProvider)
    _PROVIDER_CLASSES.update({"llm": ChatLlmProvider, "mock_llm": MockAgentProvider})


def resolve_provider(
    name: str = "",
    *,
    feature_id: str | None = None,
) -> tuple[Any, str]:
    """Resolve a provider instance for an agent.

    Selection order: explicit ``name`` (agent.provider) → the
    ``AI_AGENT_LLM_PROVIDER`` setting → the linked feature's default provider.
    Returns ``(provider, reason)``; ``provider`` is None when nothing is
    configured (callers terminate the run with ``provider_not_configured``).
    """
    register_agent_providers()

    provider_name = (name or "").strip().lower()
    if not provider_name:
        provider_name = (getattr(settings, "AI_AGENT_LLM_PROVIDER", "") or "").strip().lower()
    if not provider_name:
        from ai_intelligence.services import get_feature_registry

        feature = get_feature_registry(FEATURE_KEY)
        if feature and feature.default_provider:
            provider_name = feature.default_provider.strip().lower()

    provider_cls = _PROVIDER_CLASSES.get(provider_name)
    if provider_cls is None:
        available = ", ".join(sorted(_PROVIDER_CLASSES)) or "none"
        return None, f"provider {provider_name!r} not registered (available: {available})"

    provider = provider_cls()
    if feature_id:
        provider.feature_id = feature_id  # per-agent telemetry attribution
    return provider, "ok"
