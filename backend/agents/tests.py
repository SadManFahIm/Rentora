"""Phase 19.0 — Agent SDK tests.

Keyed off the production defaults:
* eager Celery (no broker) → tasks run synchronously
* ``mock_llm`` is a TEST ADAPTER: tests enable it explicitly, and a test
  proves production refuses it
* tool registry is process-global → each test class re-registers clean tools
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from ai_intelligence.models import AIExecutionLog, EvaluationRun
from ai_intelligence.services import (
    activate_prompt_version,
    create_prompt,
    register_feature,
)

from .errors import ProposalError
from .models import (
    AgentConversation,
    AgentProposal,
    AgentRun,
)
from .services import (
    apply_proposal,
    approve_proposal,
    create_agent_eval_run,
    create_conversation,
    create_proposal,
    create_run,
    register_agent,
    reject_proposal,
)
from .session import AgentSession, sanitize_message_text
from .tasks import execute_agent_run
from .tasks import expire_proposals as expire_task
from .tools import AgentTool, AgentToolRegistry, ToolValidationError, register_builtin_tools

User = get_user_model()


class AgentTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@rentora.dev", password="test12345"
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@rentora.dev", password="test12345", is_staff=True
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@rentora.dev",
            password="test12345",
            is_staff=True,
            role="admin",
        )
        self.other = User.objects.create_user(
            username="other", email="other@rentora.dev", password="test12345"
        )
        register_feature("rentora.agent", "AI Agents", category="agent", is_enabled=True)
        register_builtin_tools()
        AgentToolRegistry.clear()
        register_builtin_tools()

    def make_agent(self, **overrides):
        defaults = dict(
            key="test.operator",
            name="Test Operator",
            status="active",
            audience="staff",
            permission="operator",
            feature_id="rentora.agent",
            prompt_key="",
            provider="mock_llm",
            system_instructions="You are a safe test agent. Be concise.",
        )
        defaults.update(overrides)
        return register_agent(**defaults)

    def make_conversation(self, agent, user=None):
        return create_conversation(agent, user or self.staff, title="t")

    def make_call_and_proposal(self, approval="any_staff", tool_name="debug.marker"):
        agent = self.make_agent(enabled_tools=[tool_name])
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        tool = AgentToolRegistry.get(tool_name)
        return run, create_proposal(
            run,
            tool,
            {"label": "hi"},
            "call-1",
            approval_required=approval,
            actor=self.owner,
        )


MOCK_SETTINGS = override_settings(
    AI_TELEMETRY_ENABLED=True,
    AGENTS_DEBUG_TOOLS=True,
    AI_AGENT_LLM_PROVIDER="mock_llm",
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@MOCK_SETTINGS
class ToolRegistryTests(AgentTestCase):
    def test_builtins_registered_with_debug_gate(self):
        self.assertTrue(AgentToolRegistry.get("rentora.info"))
        self.assertTrue(AgentToolRegistry.get("debug.echo"))
        self.assertTrue(AgentToolRegistry.get("debug.marker"))

    def test_factory_register_requires_valid_capability(self):
        with self.assertRaises(ValueError):
            AgentTool(
                name="x",
                description="x",
                input_schema={},
                capability="nope",
                executor=lambda **kw: {},
            )
        AgentToolRegistry.clear()
        register_builtin_tools()

    def test_schema_validation(self):
        def exec(_context, name="", size=0):
            return {"ok": True, "data": {"name": name, "size": size}}

        AgentToolRegistry.register(
            AgentTool(
                name="test.tool",
                description="t",
                input_schema={
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}, "size": {"type": "integer"}},
                },
                capability="read_only",
                executor=exec,
            )
        )
        try:
            AgentToolRegistry.verify_arguments("test.tool", {"name": "x", "size": 1})
            with self.assertRaises(ToolValidationError):
                AgentToolRegistry.verify_arguments("test.tool", {"size": "not-int"})
            with self.assertRaises(ToolValidationError):
                AgentToolRegistry.verify_arguments("test.tool", {"unexpected": 1})
        finally:
            AgentToolRegistry._tools.pop("test.tool", None)

    def test_executor_wraps_failure(self):
        tool = AgentTool(
            name="test.boom",
            description="b",
            input_schema={},
            capability="read_only",
            executor=lambda **kw: (_ for _ in ()).throw(RuntimeError("kaput")),
        )
        outcome = tool.execute({}, {"actor": None})
        self.assertFalse(outcome["ok"])
        self.assertIn("kaput", outcome["error"])


# ---------------------------------------------------------------------------
# Session — core loop
# ---------------------------------------------------------------------------


@MOCK_SETTINGS
class SessionLoopTests(AgentTestCase):
    def test_text_only_run_completes(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "Hello", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "usage", "input_tokens": 10, "output_tokens": 5},
            {"type": "text", "content": "Hi there"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.input_tokens, 10)
        self.assertEqual(run.output_tokens, 5)
        self.assertEqual(run.turn_count, 2)
        msgs = list(conv.messages.order_by("sequence"))
        self.assertEqual(msgs[-1].role, "assistant")
        self.assertEqual(msgs[-1].content, "Hi there")

    def test_read_tool_executes_and_is_audited(self):
        agent = self.make_agent(enabled_tools=["rentora.info"])
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "what can you do?", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "rentora.info", "arguments": {}},
            {"type": "text", "content": "I can introspect."},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        calls = list(run.tool_calls.all())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool_name, "rentora.info")
        self.assertEqual(calls[0].permission_decision, "read_allowed")
        self.assertEqual(calls[0].execution_status, "executed")
        self.assertTrue(calls[0].result.get("ok"))
        # assistant frame + tool message + final text preserved in order
        roles = [m.role for m in conv.messages.order_by("sequence")]
        self.assertIn("assistant", roles)
        self.assertIn("tool", roles)

    def test_state_changing_tool_creates_proposal_not_execution(self):
        agent = self.make_agent(enabled_tools=["debug.marker"])
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "mark it", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "debug.marker", "arguments": {"label": "hello"}},
            {"type": "text", "content": "Proposal pending."},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        call = run.tool_calls.get(tool_name="debug.marker")
        self.assertEqual(call.permission_decision, "proposed")
        self.assertEqual(call.execution_status, "proposed")
        proposal = AgentProposal.objects.get(tool_call=call)
        self.assertEqual(proposal.status, "pending")
        self.assertEqual(proposal.approval_required, "any_staff")
        self.assertEqual(proposal.action["tool"], "debug.marker")

    def test_high_risk_requires_admin_approval(self):
        AgentToolRegistry.register(
            AgentTool(
                name="test.highrisk",
                description="h",
                input_schema={},
                capability="high_risk",
                executor=lambda **kw: {"ok": True, "data": {}},
            )
        )
        try:
            agent = self.make_agent(permission="admin", enabled_tools=["test.highrisk"])
            conv = self.make_conversation(agent)
            run, _ = create_run(conv, "go", actor=self.owner)
            run.metadata["mock_plan"] = [
                {"type": "tool_call", "name": "test.highrisk", "arguments": {}},
                {"type": "text", "content": "ok"},
            ]
            run.save()
            AgentSession(conv, actor=self.owner).execute(run)
            proposal = AgentProposal.objects.get(run=run)
            self.assertEqual(proposal.approval_required, "admin")
        finally:
            AgentToolRegistry._tools.pop("test.highrisk", None)

    def test_unregistered_and_denied_tools(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "not.real", "arguments": {}},
            {"type": "text", "content": "done"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.tool_call_count, 0)
        # denied call recorded
        tool_msgs = conv.messages.filter(role="tool")
        self.assertGreater(tool_msgs.count(), 0)

    def test_allowlist_denies_tool(self):
        agent = self.make_agent(enabled_tools=["rentora.info"])
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "debug.echo", "arguments": {"text": "hi"}},
            {"type": "text", "content": "not allowed"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        self.assertEqual(run.tool_calls.count(), 0)
        self.assertEqual(run.status, "completed")

    def test_viewer_permission_cannot_request_state_change(self):
        agent = self.make_agent(permission="viewer", enabled_tools=["debug.marker"])
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "debug.marker", "arguments": {}},
            {"type": "text", "content": "nope"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(AgentProposal.objects.filter(run=run).count(), 0)
        self.assertEqual(run.status, "completed")

    def test_max_turns_guardrail(self):
        agent = self.make_agent(max_turns=2)
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "loop", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "tool_call", "name": "not.real", "arguments": {}},
            {"type": "tool_call", "name": "not.real", "arguments": {}},
            {"type": "tool_call", "name": "not.real", "arguments": {}},
            {"type": "text", "content": "never reached"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "terminated")
        self.assertEqual(run.termination_reason, "max_turns_exceeded")
        self.assertNotEqual(run.turn_count, 0)

    def test_consecutive_tool_failures_guardrail(self):
        agent = self.make_agent()
        with override_settings(AGENTS_MAX_CONSECUTIVE_TOOL_FAILURES=2):
            conv = self.make_conversation(agent)
            run, _ = create_run(conv, "x", actor=self.owner)
            run.metadata["mock_plan"] = [
                {"type": "tool_call", "name": "not.real", "arguments": {}},
                {"type": "tool_call", "name": "not.real", "arguments": {}},
                {"type": "text", "content": "never"},
            ]
            run.save()
            AgentSession(conv, actor=self.owner).execute(run)
            run.refresh_from_db()
            self.assertEqual(run.status, "terminated")
            self.assertEqual(run.termination_reason, "consecutive_tool_failures")

    def test_provider_failure_fails_run(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [{"type": "error", "reason": "boom upstream"}]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.termination_reason, "provider_failure")
        self.assertIn("boom", run.error_message)

    def test_max_cost_guardrail(self):
        agent = self.make_agent(max_cost_usd=Decimal("0.000001"))
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [
            {
                "type": "usage",
                "input_tokens": 1000,
                "output_tokens": 1000,
                "cost_usd": "0.0001",
            },
            {"type": "text", "content": "never"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "terminated")
        self.assertEqual(run.termination_reason, "max_cost_exceeded")

    def test_no_provider_configured_terminates_safely(self):
        agent = self.make_agent()  # provider=mock_llm on agent
        agent.provider = ""
        agent.save()
        with override_settings(AI_AGENT_LLM_PROVIDER="", ENVIRONMENT="production"):
            conv = self.make_conversation(agent)
            run, _ = create_run(conv, "x", actor=self.owner)
            AgentSession(conv, actor=self.owner).execute(run)
            run.refresh_from_db()
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.termination_reason, "provider_not_configured")

    def test_mock_provider_refused_in_production(self):
        agent = self.make_agent()
        with override_settings(ENVIRONMENT="production", AGENTS_DEBUG_TOOLS=False):
            conv = self.make_conversation(agent)
            run, _ = create_run(conv, "x", actor=self.owner)
            AgentSession(conv, actor=self.owner).execute(run)
            run.refresh_from_db()
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.termination_reason, "provider_not_configured")

    def test_audience_and_inactive_agent_checks(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        agent.status = "disabled"
        agent.save(update_fields=["status"])
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("agent_not_active", run.termination_reason)

    def test_feature_unavailable_blocks_run(self):
        from ai_intelligence.models import AIFeatureRegistry

        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        AIFeatureRegistry.objects.filter(feature_id="rentora.agent").update(is_enabled=False)
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIn("feature_unavailable", run.termination_reason)

    def test_transcript_sanitization(self):
        dirty = "\x00hidden\r\n visible"
        clean = sanitize_message_text(dirty, limit=50)
        self.assertNotIn("\x00", clean)
        self.assertNotIn("\r", clean)

    def test_deep_structured_tool_result_survives_persistence(self):
        """A deep tool envelope (ok -> data -> rows -> row -> fields) must not
        be nulled out by the outcome sanitizer or truncated by the message cap
        — the LLM and any consumer depend on those grounded facts."""
        import json

        def exec(context, label="deep"):
            return {
                "ok": True,
                "data": {
                    "rows": [
                        {
                            "id": 42,
                            "title": "একটি বাংলা রুম",
                            "address": "House 12, Road 4, Uttara 47, Dhaka 1230",
                            "price_bdt": 12000.0,
                            "tags": ["wifi", "furnished"],
                        }
                    ]
                },
            }

        AgentToolRegistry.register(
            AgentTool(
                name="test.deepresult",
                description="d",
                input_schema={"type": "object", "properties": {"label": {"type": "string"}}},
                capability="read_only",
                executor=exec,
            )
        )
        try:
            agent = self.make_agent(enabled_tools=["test.deepresult"])
            conv = self.make_conversation(agent)
            run, _ = create_run(conv, "deep", actor=self.owner)
            run.metadata["mock_plan"] = [
                {"type": "tool_call", "name": "test.deepresult", "arguments": {}},
                {"type": "text", "content": "done"},
            ]
            run.save()
            AgentSession(conv, actor=self.owner).execute(run)
            run.refresh_from_db()
            self.assertEqual(run.status, "completed")

            call = run.tool_calls.get(tool_name="test.deepresult")
            self.assertTrue(call.result.get("ok"))
            stored_card = call.result["data"]["rows"][0]
            self.assertEqual(stored_card["id"], 42)
            self.assertEqual(stored_card["price_bdt"], 12000.0)
            self.assertEqual(stored_card["title"], "একটি বাংলা রুম")

            tool_msg = conv.messages.filter(role="tool").order_by("-sequence").first()
            parsed = json.loads(tool_msg.content)
            self.assertTrue(parsed["ok"])
            self.assertEqual(parsed["data"]["rows"][0]["id"], 42)
        finally:
            AgentToolRegistry._tools.pop("test.deepresult", None)

    def test_telemetry_rows_created_and_enriched(self):
        from ai_intelligence.services import register_feature as rf

        rf("rentora.agent", "AI Agents", is_enabled=True)
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [
            {"type": "usage", "input_tokens": 100, "output_tokens": 25},
            {"type": "text", "content": "done"},
        ]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        logs = AIExecutionLog.objects.filter(feature_key="rentora.agent")
        self.assertGreaterEqual(logs.count(), 2)
        for log in logs:
            self.assertEqual(log.status, "success")
            self.assertIn(log.provider, ("mock_llm",))
            self.assertEqual(log.prompt_key, run.prompt_key or "")

    def test_prompt_registry_path(self):
        create_prompt(
            prompt_key="rentora.test.prompt",
            name="TP",
            template="You are {agent_name}. Be safe.",
            variables={},
        )
        activate_prompt_version("rentora.test.prompt", 1)
        agent = self.make_agent(prompt_key="rentora.test.prompt")
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [{"type": "text", "content": "ok"}]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.prompt_key, "rentora.test.prompt")
        self.assertEqual(run.prompt_version, 1)


# ---------------------------------------------------------------------------
# Proposal lifecycle
# ---------------------------------------------------------------------------


@MOCK_SETTINGS
class ProposalLifecycleTests(AgentTestCase):
    def test_approve_then_apply_applies_exactly_once(self):
        _, proposal = self.make_call_and_proposal()
        approve_proposal(proposal, self.staff, note="fine")
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "approved")

        applied = apply_proposal(proposal, actor=self.staff)
        applied.refresh_from_db()
        self.assertEqual(applied.status, "applied")
        self.assertTrue(applied.application_result.get("ok"))
        self.assertIsNotNone(applied.applied_at)

        # Replay is a no-op (idempotent) — status and result unchanged.
        again = apply_proposal(applied, actor=self.staff)
        self.assertEqual(again.status, "applied")
        self.assertEqual(again.application_result, applied.application_result)

    def test_cannot_apply_without_approval(self):
        _, proposal = self.make_call_and_proposal()
        with self.assertRaises(ProposalError):
            apply_proposal(proposal, actor=self.staff)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")

    def test_reject_blocks_apply(self):
        _, proposal = self.make_call_and_proposal()
        reject_proposal(proposal, self.staff, reason="not needed")
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "rejected")
        with self.assertRaises(ProposalError):
            apply_proposal(proposal, actor=self.staff)

    def test_admin_approval_required_for_high_risk(self):
        _, proposal = self.make_call_and_proposal(approval="admin")
        with self.assertRaises(ProposalError):
            approve_proposal(proposal, self.staff)
        approve_proposal(proposal, self.admin)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "approved")

    def test_expiry_via_task(self):
        _, proposal = self.make_call_and_proposal()
        AgentProposal.objects.filter(pk=proposal.pk).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        result = expire_task()
        self.assertGreaterEqual(result["expired"], 1)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "expired")
        with self.assertRaises(ProposalError):
            apply_proposal(proposal, actor=self.staff)

    def test_expired_proposal_cannot_approve(self):
        _, proposal = self.make_call_and_proposal()
        AgentProposal.objects.filter(pk=proposal.pk).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        expire_task()  # marks expired
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "expired")
        with self.assertRaises(ProposalError):
            approve_proposal(proposal, self.admin)


# ---------------------------------------------------------------------------
# Evaluation + integration
# ---------------------------------------------------------------------------


@MOCK_SETTINGS
class IntegrationTests(AgentTestCase):
    def test_eval_run_hook_creates_pending_snapshot(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [{"type": "text", "content": "ok"}]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        eval_run = create_agent_eval_run(run.pk, feature_id="rentora.agent")
        self.assertIsInstance(eval_run, EvaluationRun)
        self.assertEqual(eval_run.status, "pending")
        self.assertEqual(eval_run.provider, "mock_llm")
        self.assertIn("agent_run_id", eval_run.metadata)

    def test_task_dispatches_eager_execution(self):
        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "hello", actor=self.owner)
        run.metadata["mock_plan"] = [{"type": "text", "content": "hey"}]
        run.save()
        execute_agent_run.delay(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        roles = [m.role for m in conv.messages.order_by("sequence")]
        self.assertEqual(roles[-1], "assistant")

    def test_failure_notifies_with_ai_alert(self):
        from notifications.models import Notification

        agent = self.make_agent()
        conv = self.make_conversation(agent)
        run, _ = create_run(conv, "x", actor=self.owner)
        run.metadata["mock_plan"] = [{"type": "error", "reason": "nope"}]
        run.save()
        AgentSession(conv, actor=self.owner).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        notif = Notification.objects.filter(user=self.staff).order_by("-id").first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.notification_type, "ai_alert")

    def test_tenant_isolation_user_cannot_see_other_conversation(self):
        agent = self.make_agent(audience="users")
        conv = self.make_conversation(agent, user=self.other)
        client = APIClient()
        client.force_authenticate(user=self.owner)
        r = client.get(f"/api/v1/agents/conversations/{conv.pk}/")
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


@MOCK_SETTINGS
class ApiTests(AgentTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_catalog_audience_filtering(self):
        self.make_agent(audience="staff")
        self.make_agent(key="public.one", name="Pub", audience="public")
        r = self.client.get("/api/v1/agents/")
        self.assertEqual(r.status_code, 200)
        keys = {a["key"] for a in r.json()}
        self.assertEqual(keys, {"public.one"})  # anonymous sees public only

    def test_conversation_send_message_run_flow(self):
        agent = self.make_agent(audience="users")
        self.client.force_authenticate(user=self.owner)
        r = self.client.post(
            "/api/v1/agents/conversations/",
            {"agent_key": agent.key, "title": "hello"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        conv_id = r.json()["id"]
        self.assertTrue(AgentConversation.objects.filter(pk=conv_id).exists())

        r2 = self.client.post(
            f"/api/v1/agents/conversations/{conv_id}/messages/",
            {"message": "hi"},
            format="json",
        )
        self.assertEqual(r2.status_code, 201)
        self.assertIn("run_key", r2.json())
        run = AgentRun.objects.get(run_key=r2.json()["run_key"])
        # Celery is eager (no broker) — the POST already executed the run.
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        conv = AgentConversation.objects.get(pk=conv_id)
        self.assertIsNotNone(conv.messages.filter(role="user").first())
        self.assertIsNotNone(conv.messages.filter(role="assistant").first())

    def test_admin_registry_is_rbac_gated(self):
        self.client.force_authenticate(user=self.owner)
        r = self.client.get("/api/v1/agents/admin/registry/")
        self.assertEqual(r.status_code, 403)
        self.client.force_authenticate(user=self.staff)
        r = self.client.get("/api/v1/agents/admin/registry/")
        self.assertEqual(r.status_code, 200)

    def test_proposal_review_endpoints_gated(self):
        self.client.force_authenticate(user=self.owner)
        r = self.client.get("/api/v1/agents/admin/proposals/")
        self.assertEqual(r.status_code, 403)

    def test_admin_proposal_approve_apply_via_api(self):
        _, proposal = self.make_call_and_proposal()
        self.client.force_authenticate(user=self.staff)
        pk = proposal.proposal_key
        r = self.client.post(f"/api/v1/agents/admin/proposals/{pk}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post(f"/api/v1/agents/admin/proposals/{pk}/apply/", {}, format="json")
        self.assertEqual(r.status_code, 200)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "applied")

    def test_public_only_agents_listed(self):
        self.make_agent(key="pub", name="P", audience="public")
        r = self.client.get("/api/v1/agents/")
        keys = {a["key"] for a in r.json()}
        self.assertIn("pub", keys)
