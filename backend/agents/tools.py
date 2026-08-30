"""Tool registry + schema verification — Phase 19.0.

Tools are the ONLY way an agent can read or change application state. This
module owns:

* ``AgentTool`` — declarative tool spec (permission/capability/audit).
* ``AgentToolRegistry`` — registration, lookup, JSON-schema verification
  (``jsonschema``) before any execution.
* built-in tools: ``rentora.info`` (read), ``debug.echo`` (read) and
  ``debug.marker`` (state-changing). Debug tools register only when
  ``AGENTS_DEBUG_TOOLS`` is set or the environment is a test suite, so a
  production deployment never exposes them by accident.

Every executed tool returns a grounded envelope::

    {"ok": True, "data": {...}}          # or
    {"ok": False, "error": "..."}

Session transcripts tag tool role messages so the model can only ever
reason over server-verified (TOOL-DERIVED) data, never fabricated state.
"""

import json
from collections.abc import Callable
from typing import Any

import jsonschema
from django.conf import settings

# --- Capability tiers (server-side permission model) -----------------------
READ_ONLY = "read_only"  # executed immediately, recorded
STATE_CHANGING = "state_changing"  # proposal + human approval required
HIGH_RISK = "high_risk"  # proposal + admin-only approval required

# Mapping: agent permission ceiling -> capabilities it may request.
PERMISSION_CAPABILITIES = {
    "viewer": {READ_ONLY},
    "operator": {READ_ONLY, STATE_CHANGING},
    "admin": {READ_ONLY, STATE_CHANGING, HIGH_RISK},
}

TYPE_READ_ONLY = "read_only"
TYPE_STATE_CHANGING = "state_changing"
TYPE_HIGH_RISK = "high_risk"

# The result envelope keys an executor must produce.
RESULT_OK = "ok"
RESULT_ERROR = "error"
RESULT_DATA = "data"


class ToolValidationError(ValueError):
    """Arguments failed JSON-schema validation or are context-invalid."""


class AgentTool:
    """Declarative description of a single tool an agent can invoke."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        capability: str,
        executor: Callable[..., dict[str, Any]],
        *,
        audit: bool = True,
        enabled: bool = True,
        owner: str = "rentora.core",
    ) -> None:
        if capability not in (READ_ONLY, STATE_CHANGING, HIGH_RISK):
            raise ValueError(f"invalid capability {capability!r}")
        self.name = name
        self.description = description
        self.input_schema = input_schema or {"type": "object", "properties": {}}
        self.capability = capability
        self.executor = executor
        self.audit = audit
        self.enabled = enabled
        self.owner = owner

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """JSON-schema verify arguments. Raises ToolValidationError."""
        try:
            jsonschema.validate(instance=arguments, schema=self.input_schema)
        except jsonschema.ValidationError as exc:
            raise ToolValidationError(
                f"arguments for {self.name} failed schema: {exc.message}"
            ) from exc
        return arguments

    def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Run the executor. Executors are expected to already have been
        schema-verified; any exception is wrapped into the error envelope."""
        try:
            result = self.executor(context=context, **arguments)
        except TypeError:
            try:
                result = self.executor(**arguments)
            except TypeError as exc:
                return {
                    RESULT_OK: False,
                    RESULT_ERROR: f"executor signature mismatch: {exc}",
                }
        except Exception as exc:
            return {RESULT_OK: False, RESULT_ERROR: f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            return {
                RESULT_OK: False,
                RESULT_ERROR: "executor must return a dictionary envelope",
            }
        result.setdefault(RESULT_OK, True)
        return result


class AgentToolRegistry:
    """In-memory registry keyed by tool name."""

    _tools: dict[str, AgentTool] = {}

    @classmethod
    def register(cls, tool: AgentTool) -> None:
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> AgentTool | None:
        return cls._tools.get(name)

    @classmethod
    def all(cls) -> list[AgentTool]:
        return sorted(cls._tools.values(), key=lambda t: t.name)

    @classmethod
    def clear(cls) -> None:
        """Reset the registry (test isolation)."""
        cls._tools.clear()

    @classmethod
    def verify_arguments(cls, name: str, arguments: dict[str, Any]) -> None:
        tool = cls.get(name)
        if tool is None:
            raise ToolValidationError(f"tool {name!r} is not registered")
        tool.validate_arguments(arguments)


# --- Built-in tools ---------------------------------------------------------


def _info_executor(context: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Static introspection tool every agent can use to self-describe."""

    tools = [
        {
            "name": t.name,
            "description": t.description,
            "capability": t.capability,
            "enabled": t.enabled,
        }
        for t in AgentToolRegistry.all()
    ]
    return {"ok": True, "data": {"available_tools": tools}}


def _echo_executor(context: dict[str, Any], text: str = "") -> dict[str, Any]:
    return {"ok": True, "data": {"echo": text[:500]}}


def _marker_executor(context: dict[str, Any], label: str = "marker") -> dict[str, Any]:
    """State-changing test stub — records via the audit log. Exists only in
    test/debug environments; never reachable in production."""
    from audit.services import log_action

    actor = context.get("actor")
    log_action(
        actor=actor,
        action="debug.marker",
        target=context.get("conversation"),
        detail=f"label={label[:200]}",
    )
    return {"ok": True, "data": {"label": label[:200], "recorded": True}}


def register_builtin_tools() -> None:
    """Register built-ins. Debug tools are gated so production has no
    executable state-changing stub."""
    AgentToolRegistry.register(
        AgentTool(
            name="rentora.info",
            description=(
                "Static introspection: list the tools this agent may call, "
                "for self-description. Safe to call anytime."
            ),
            input_schema={
                "type": "object",
                "properties": {},
            },
            capability=READ_ONLY,
            executor=_info_executor,
            owner="rentora.core",
        )
    )
    debug_enabled = getattr(settings, "AGENTS_DEBUG_TOOLS", False) or settings.ENVIRONMENT == "test"
    if debug_enabled:
        AgentToolRegistry.register(
            AgentTool(
                name="debug.echo",
                description="Echo text back verbatim (debug/test only).",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "maxLength": 500, "default": ""}},
                },
                capability=READ_ONLY,
                executor=_echo_executor,
                owner="rentora.debug",
            )
        )
        AgentToolRegistry.register(
            AgentTool(
                name="debug.marker",
                description="Record a marker in the audit log (debug/test only).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "maxLength": 200, "default": "marker"}
                    },
                },
                capability=STATE_CHANGING,
                executor=_marker_executor,
                owner="rentora.debug",
            )
        )

    # Domain tools are registered through this single SDK registration path so
    # every agent run sees a complete, current registry. Optional apps degrade
    # to absent (the registry refuses unregistered tools before execution).
    try:
        from property_intelligence.agent_tool import register_property_intelligence_tool

        register_property_intelligence_tool()
    except Exception:
        pass  # property intelligence app not installed


def render_results_json(results: list[dict[str, Any]]) -> str:
    """Compact, safe rendering of a tool result transcript fragment."""
    return json.dumps(results, ensure_ascii=True, default=str)[:4000]
