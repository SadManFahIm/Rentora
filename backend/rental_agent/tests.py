"""Phase 19.2 — AI Rental Agent tests.

Covers:
* tool registration + JSON schema (5 domain tools + capability ceiling)
* groundedness of every executor (search / room / commute / price / bookmark)
* tenant self-consent for ``bookmark.create`` (apply, idempotency, ownership,
  reject, expiry, sibling dedupe, cross-user safety)
* session integration (eager Celery + mock plan) through the SDK
* API surface: auth required, flag-off gating, conversation ownership,
  consent endpoints + run status
* seeding command idempotency
"""

from __future__ import annotations

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status as http_status
from rest_framework.test import APIClient

from agents.models import Agent, AgentProposal, AgentRun, AgentToolCall
from agents.services import (
    create_conversation,
    create_proposal,
    create_run,
    get_agent,
    register_agent,
)
from agents.session import AgentSession
from agents.tools import (
    READ_ONLY,
    RESULT_OK,
    STATE_CHANGING,
    AgentToolRegistry,
    register_builtin_tools,
)
from ai_intelligence.services import register_feature
from feature_flags.models import FeatureFlag, invalidate_cache
from pricing.models import MarketStat
from rooms.models import Room, RoomImage
from wishlist.models import Wishlist

from .services import (
    ConsentError,
    conversation_payload,
    self_consent_and_apply,
    self_reject,
)
from .tools import (
    BOOKMARK_TOOL,
    COMMUTE_TOOL,
    PRICE_TOOL,
    ROOM_TOOL,
    SEARCH_TOOL,
)

User = get_user_model()

FLAG_KEY = "ai.rental_agent"
FEATURE_ID = "rentora.rental_agent"
AGENT_KEY = "ai.rental_agent"
ENABLED_TOOLS = [
    SEARCH_TOOL,
    ROOM_TOOL,
    COMMUTE_TOOL,
    PRICE_TOOL,
    BOOKMARK_TOOL,
    "property.intelligence",
]

MOCK_SETTINGS = override_settings(
    AGENTS_DEBUG_TOOLS=True,
    AI_AGENT_LLM_PROVIDER="mock_llm",
)


def make_user(username="tenant"):
    return User.objects.create_user(
        username=username, email=f"{username}@rentora.dev", password="test12345"
    )


def make_room(owner, **overrides):
    fields = dict(
        title="Mirpur 10 Shared Room",
        description="Clean furnished room near Mirpur 10 metro, wifi + AC.",
        room_type="single",
        price=10000,
        area="Mirpur",
        address="House 12, Road 4, Mirpur 10, Dhaka 1216",
        lat=23.806,
        lng=90.368,
        amenities=["wifi", "attached bathroom", "kitchen", "furnished", "AC"],
        size_sqft=240,
    )
    fields.update(overrides)
    return Room.objects.create(owner=owner, **fields)


def attach_primary_image(room):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(buffer, format="PNG")
    from django.core.files.uploadedfile import SimpleUploadedFile

    return RoomImage.objects.create(
        room=room,
        is_primary=True,
        image=SimpleUploadedFile("a.png", buffer.getvalue(), "image/png"),
    )


def make_market(area="Mirpur", room_type="single", avg=12000, sample=12):
    return MarketStat.objects.create(
        area=area,
        room_type=room_type,
        avg_price=avg,
        median_price=avg,
        min_price=avg * 0.8,
        max_price=avg * 1.2,
        percentile_25=avg * 0.9,
        percentile_75=avg * 1.1,
        sample_size=sample,
    )


def enable_rental_feature():
    register_feature(
        feature_id=FEATURE_ID,
        name="AI Rental Agent",
        category="agent",
        is_enabled=True,
        feature_flag_key=FLAG_KEY,
        default_provider="mock_llm",
    )
    FeatureFlag.objects.update_or_create(
        key=FLAG_KEY,
        defaults={"status": "enabled", "rollout_percentage": 100},
    )
    invalidate_cache(FLAG_KEY)


def rental_agent(**overrides):
    defaults = dict(
        key=AGENT_KEY,
        name="Rentora AI Rental Agent",
        status="active",
        audience="users",
        permission="operator",
        feature_id=FEATURE_ID,
        prompt_key="",
        provider="mock_llm",
        system_instructions=(
            "You are the Rentora rental agent. Only answer from tool results. "
            "Never invent a room, price or commute time. Ask for consent "
            "before calling bookmark.create."
        ),
        enabled_tools=ENABLED_TOOLS,
    )
    defaults.update(overrides)
    return register_agent(**defaults)


@MOCK_SETTINGS
class RentalAgentTestCase(TestCase):
    def setUp(self):
        self.tenant = make_user("tenant")
        self.other = make_user("other")
        self.owner = make_user("room_owner")
        enable_rental_feature()
        AgentToolRegistry.clear()
        register_builtin_tools()
        self.room = make_room(self.owner)
        self.agent = rental_agent()

    def tearDown(self):
        AgentToolRegistry.clear()

    def make_conversation(self, user=None):
        return create_conversation(self.agent, user or self.tenant, title="AI Rental Agent")

    def make_bookmark_proposal(self, conversation=None, room=None):
        conv = conversation or self.make_conversation()
        run, _ = create_run(conv, "সেভ করে দাও", actor=self.tenant)
        tool = AgentToolRegistry.get(BOOKMARK_TOOL)
        return run, create_proposal(
            run,
            tool,
            {"room_id": (room or self.room).pk},
            "call-bm-1",
            approval_required="any_staff",
            actor=self.tenant,
        )


# ---------------------------------------------------------------------------
# Tools — registration + schema
# ---------------------------------------------------------------------------


class ToolRegistrationTests(RentalAgentTestCase):
    def test_five_domain_tools_registered(self):
        for name in (SEARCH_TOOL, ROOM_TOOL, COMMUTE_TOOL, PRICE_TOOL, BOOKMARK_TOOL):
            tool = AgentToolRegistry.get(name)
            self.assertIsNotNone(tool, name)
            self.assertTrue(tool.enabled)

    def test_capability_ceiling(self):
        self.assertEqual(AgentToolRegistry.get(SEARCH_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(ROOM_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(COMMUTE_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(PRICE_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(BOOKMARK_TOOL).capability, STATE_CHANGING)

    def test_schema_validation(self):
        search = AgentToolRegistry.get(SEARCH_TOOL)
        search.validate_arguments({"query": "উত্তরা", "budget_max": 12000, "top_k": 3})
        search.validate_arguments({})  # everything optional
        from agents.tools import ToolValidationError

        with self.assertRaises(ToolValidationError):
            search.validate_arguments({"top_k": 200})
        with self.assertRaises(ToolValidationError):
            search.validate_arguments({"room_type": "penthouse"})

        room = AgentToolRegistry.get(ROOM_TOOL)
        with self.assertRaises(ToolValidationError):
            room.validate_arguments({})  # room_id required

        commute = AgentToolRegistry.get(COMMUTE_TOOL)
        commute.validate_arguments({"to_area": "Uttara", "mode": "transit"})
        with self.assertRaises(ToolValidationError):
            commute.validate_arguments({"to_area": "Uttara", "mode": "fly"})

    def test_bookmark_schema_rejects_extra_user_arg(self):
        """The executor must never accept a user argument — the acting user
        always comes from the server context, so cross-account writes are
        impossible even with a tampered call."""
        tool = AgentToolRegistry.get(BOOKMARK_TOOL)
        from agents.tools import ToolValidationError

        with self.assertRaises(ToolValidationError):
            tool.validate_arguments({"room_id": self.room.pk, "user_id": self.other.pk})


# ---------------------------------------------------------------------------
# Executors — groundedness
# ---------------------------------------------------------------------------


class SearchToolTests(RentalAgentTestCase):
    def test_search_returns_grounded_cards_only(self):
        make_room(self.owner, title="Gulshan Budget", price=8000, area="Gulshan")
        dhan = make_room(self.owner, title="Dhanmondi Studio", price=20000, area="Dhanmondi")

        tool = AgentToolRegistry.get(SEARCH_TOOL)
        outcome = tool.execute(
            {"area": "Mirpur", "budget_max": 10000, "top_k": 10}, {"user": self.tenant}
        )
        self.assertTrue(outcome[RESULT_OK])
        self.assertEqual(len(outcome["data"]["rooms"]), 1)
        self.assertEqual(outcome["data"]["rooms"][0]["id"], self.room.pk)
        self.assertEqual(outcome["data"]["rooms"][0]["price_bdt"], float(self.room.price))
        self.assertEqual(outcome["data"]["filters"]["areas"], ["Mirpur"])

        # The un-matching Gulshan/Dhanmondi rooms are never discoverable past
        # the hard filters (budget/area).
        self.assertNotIn(dhan.pk, [c["id"] for c in outcome["data"]["rooms"]])

    def test_search_no_hits_returns_empty_not_error(self):
        tool = AgentToolRegistry.get(SEARCH_TOOL)
        outcome = tool.execute({"area": "Savar", "budget_max": 1}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])
        self.assertEqual(outcome["data"]["rooms"], [])
        self.assertEqual(outcome["data"]["total_count"], 0)
        self.assertEqual(outcome["data"]["kind"], "none")

    def test_search_bangla_free_text_budget(self):
        make_room(self.owner, title="Uttara AC Room", price=11000, area="Uttara")
        tool = AgentToolRegistry.get(SEARCH_TOOL)
        outcome = tool.execute(
            {"query": "উত্তরা ১২ হাজারের মধ্যে furnished room", "top_k": 5},
            {"user": self.tenant},
        )
        # Grounded: every returned card is a real room within the parsed
        # budget — nothing is ever invented.
        self.assertTrue(outcome[RESULT_OK])
        self.assertGreater(len(outcome["data"]["rooms"]), 0)
        for card in outcome["data"]["rooms"]:
            self.assertLessEqual(card["price_bdt"], 12000)
            self.assertTrue(Room.objects.filter(pk=card["id"]).exists())


class RoomToolTests(RentalAgentTestCase):
    def test_room_detail_grounded_and_public_safe(self):
        attach_primary_image(self.room)
        make_market()
        tool = AgentToolRegistry.get(ROOM_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])
        data = outcome["data"]
        self.assertEqual(data["title"], self.room.title)
        self.assertEqual(data["price_bdt"], float(self.room.price))
        self.assertIn("insights", data)
        self.assertTrue(data["insights"]["price"]["available"])
        # Public-safe: no owner PII / addresses beyond what cards expose.
        self.assertNotIn("owner", data)

    def test_room_unavailable_reports_honest_not_error(self):
        self.room.is_available = False
        self.room.save(update_fields=["is_available"])
        tool = AgentToolRegistry.get(ROOM_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])
        self.assertFalse(outcome["data"]["available"])

    def test_room_unknown_is_error(self):
        tool = AgentToolRegistry.get(ROOM_TOOL)
        outcome = tool.execute({"room_id": 999999}, {"user": self.tenant})
        self.assertFalse(outcome[RESULT_OK])


class CommuteToolTests(RentalAgentTestCase):
    def test_walking_estimate_between_known_areas(self):
        tool = AgentToolRegistry.get(COMMUTE_TOOL)
        outcome = tool.execute(
            {"from_area": "Dhanmondi", "to_area": "Mirpur", "mode": "walking"},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        self.assertTrue(outcome["data"]["available"])
        self.assertIn("minutes", outcome["data"])
        self.assertTrue(outcome["data"]["minutes"] > 0)

    def test_room_origin_uses_real_coordinates(self):
        tool = AgentToolRegistry.get(COMMUTE_TOOL)
        outcome = tool.execute(
            {"room_id": self.room.pk, "to_area": "Mirpur", "mode": "walking"},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        self.assertEqual(outcome["data"]["origin"], self.room.title)

    def test_unknown_destination_is_not_an_error(self):
        tool = AgentToolRegistry.get(COMMUTE_TOOL)
        outcome = tool.execute(
            {"from_area": "Dhanmondi", "to_area": "NotARealArea", "mode": "walking"},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        self.assertFalse(outcome["data"]["available"])

    def test_transit_without_corridor_is_honest_unavailable(self):
        tool = AgentToolRegistry.get(COMMUTE_TOOL)
        outcome = tool.execute(
            {"from_area": "Savar", "to_area": "Uttara", "mode": "transit"},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        # minutes is None (no MRT corridor) — the model must say so, never
        # invent a number.
        self.assertFalse(outcome["data"]["available"])
        self.assertIsNone(outcome["data"]["minutes"])


class PriceToolTests(RentalAgentTestCase):
    def test_market_comparison_grounded(self):
        make_market(area="Mirpur", room_type="single", avg=12000, sample=12)
        tool = AgentToolRegistry.get(PRICE_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])
        data = outcome["data"]
        self.assertTrue(data["available"])
        self.assertIn("classification", data)
        self.assertEqual(data["listed_price"], float(self.room.price))

    def test_no_market_segment_is_truthful_unavailable(self):
        tool = AgentToolRegistry.get(PRICE_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])  # NOT ok:false — this is a valid answer
        self.assertFalse(outcome["data"]["available"])


class BookmarkToolTests(RentalAgentTestCase):
    def test_bookmark_saves_for_context_user_only(self):
        tool = AgentToolRegistry.get(BOOKMARK_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(outcome[RESULT_OK])
        self.assertTrue(outcome["data"]["saved"])
        self.assertTrue(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_bookmark_idempotent(self):
        tool = AgentToolRegistry.get(BOOKMARK_TOOL)
        tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        second = tool.execute({"room_id": self.room.pk}, {"user": self.tenant})
        self.assertTrue(second[RESULT_OK])
        self.assertTrue(second["data"]["already_saved"])
        self.assertEqual(Wishlist.objects.filter(user=self.tenant, room=self.room).count(), 1)

    def test_bookmark_requires_authenticated_user(self):
        tool = AgentToolRegistry.get(BOOKMARK_TOOL)
        outcome = tool.execute({"room_id": self.room.pk}, {"user": None})
        self.assertFalse(outcome[RESULT_OK])
        self.assertIn("authenticated", outcome["error"].lower())


# ---------------------------------------------------------------------------
# Tenant self-consent for bookmark.create
# ---------------------------------------------------------------------------


class ConsentTests(RentalAgentTestCase):
    def test_self_consent_applies_once_and_saves(self):
        _, proposal = self.make_bookmark_proposal()
        applied = self_consent_and_apply(self.tenant, proposal)
        applied.refresh_from_db()
        self.assertEqual(applied.status, "applied")
        self.assertTrue(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())
        self.assertTrue(applied.application_result.get("ok"))
        self.assertEqual(applied.reviewed_by, self.tenant)

    def test_self_consent_is_idempotent_replay_safe(self):
        _, proposal = self.make_bookmark_proposal()
        self_consent_and_apply(self.tenant, proposal)
        proposal.refresh_from_db()
        replay = self_consent_and_apply(self.tenant, proposal)
        self.assertEqual(replay.status, "applied")
        self.assertEqual(Wishlist.objects.filter(user=self.tenant, room=self.room).count(), 1)

    def test_self_consent_requires_conversation_owner(self):
        _, proposal = self.make_bookmark_proposal()
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self_consent_and_apply(self.other, proposal)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")
        self.assertFalse(Wishlist.objects.filter(user=self.other, room=self.room).exists())

    def test_self_reject_records_reviewer_and_reason(self):
        _, proposal = self.make_bookmark_proposal()
        rejected = self_reject(self.tenant, proposal, reason="দর বেশি")
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.reviewed_by, self.tenant)
        self.assertIn("দর বেশি", rejected.rejection_reason)
        self.assertFalse(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_rejected_proposal_can_never_be_applied(self):
        _, proposal = self.make_bookmark_proposal()
        self_reject(self.tenant, proposal)
        proposal.refresh_from_db()
        with self.assertRaises(ConsentError):
            self_consent_and_apply(self.tenant, proposal)
        self.assertFalse(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_expired_proposal_cannot_be_consented(self):
        _, proposal = self.make_bookmark_proposal()
        proposal.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        proposal.save(update_fields=["expires_at"])
        with self.assertRaises(ConsentError):
            self_consent_and_apply(self.tenant, proposal)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")
        self.assertFalse(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_sibling_pending_proposals_dedupe_on_consent(self):
        _, proposal = self.make_bookmark_proposal(room=self.room)
        _, proposal2 = self.make_bookmark_proposal(room=self.room)
        self_consent_and_apply(self.tenant, proposal)
        proposal.refresh_from_db()
        proposal2.refresh_from_db()
        self.assertEqual(proposal.status, "applied")
        self.assertEqual(proposal2.status, "expired")

    def test_unsupported_proposal_type_rejected(self):
        _, proposal = self.make_bookmark_proposal()
        # Flip the proposal's action to a different tool — as if tampered.
        proposal.action = {"tool": "other.state.change", "arguments": {}}
        proposal.save(update_fields=["action"])
        with self.assertRaises(ConsentError):
            self_consent_and_apply(self.tenant, proposal)
        self.assertFalse(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())


# ---------------------------------------------------------------------------
# Session integration (eager Celery) + enrichment payload
# ---------------------------------------------------------------------------


class SessionIntegrationTests(RentalAgentTestCase):
    def _run_plan(self, conv, plan):
        run, _ = create_run(conv, "উত্তরায় রুম দেখাও", actor=self.tenant)
        run.metadata["mock_plan"] = plan
        run.save(update_fields=["metadata"])
        AgentSession(conv, actor=self.tenant).execute(run)
        run.refresh_from_db()
        return run

    def test_search_thread_grounded_via_session_and_enriched_payload(self):
        conv = self.make_conversation()
        run = self._run_plan(
            conv,
            [
                {
                    "type": "tool_call",
                    "name": SEARCH_TOOL,
                    "arguments": {"area": "Mirpur", "top_k": 3},
                },
                {"type": "text", "content": "মিরপুরে এই রুমগুলো পেয়েছি।"},
            ],
        )
        self.assertEqual(run.status, "completed")
        call = AgentToolCall.objects.get(run=run, tool_name=SEARCH_TOOL)
        self.assertEqual(call.permission_decision, "read_allowed")
        self.assertEqual(call.execution_status, "executed")
        self.assertTrue(call.result.get("ok"))

        payload = conversation_payload(conv)
        self.assertEqual(payload["agent"]["key"], AGENT_KEY)
        self.assertTrue(payload["feature_enabled"])
        # The assistant text carries the grounded room card right after the
        # tool result.
        assistant = [m for m in payload["messages"] if m["role"] == "assistant"]
        self.assertTrue(assistant)
        self.assertEqual(assistant[0]["cards"][0]["id"], self.room.pk)
        # Suggestions derived from the last search result — not random.
        self.assertTrue(any(chip["label"] == "আরও রুম" for chip in payload["suggestions"]))

    def test_bookmark_plan_creates_pending_proposal_and_shows_in_payload(self):
        conv = self.make_conversation()
        run = self._run_plan(
            conv,
            [
                {
                    "type": "tool_call",
                    "name": BOOKMARK_TOOL,
                    "arguments": {"room_id": self.room.pk},
                },
                {"type": "text", "content": "সেভ করতে হলে আপনার অনুমতি লাগবে।"},
            ],
        )
        self.assertEqual(run.status, "completed")
        proposal = AgentProposal.objects.get(run=run, proposal_type=BOOKMARK_TOOL)
        self.assertEqual(proposal.status, "pending")
        self.assertEqual(proposal.approval_required, "any_staff")

        payload = conversation_payload(conv)
        self.assertEqual(payload["proposals"][0]["key"], str(proposal.proposal_key))
        self.assertEqual(payload["proposals"][0]["room"]["id"], self.room.pk)

        # Full consent round-trip after the session proposed the save.
        applied = self_consent_and_apply(self.tenant, proposal)
        self.assertEqual(applied.status, "applied")
        self.assertTrue(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_disabled_feature_blocks_session(self):
        conv = self.make_conversation()
        run, _ = create_run(conv, "রুম দেখাও", actor=self.tenant)
        FeatureFlag.objects.filter(key=FLAG_KEY).update(status="disabled")
        invalidate_cache(FLAG_KEY)
        run.metadata["mock_plan"] = [{"type": "text", "content": "x"}]
        run.save(update_fields=["metadata"])
        AgentSession(conv, actor=self.tenant).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.termination_reason, "feature_unavailable")


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


class ApiTests(RentalAgentTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.tenant)

    def test_chat_requires_authentication(self):
        resp = self.client.post("/api/v1/rental/chat/", {"message": "রুম দেখাও"})
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_chat_starts_conversation_and_runs_eagerly(self):
        self._auth()
        resp = self.client.post("/api/v1/rental/chat/", {"message": "রুম দেখাও"})
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        self.assertIn("conversation_id", resp.data)
        run = AgentRun.objects.get(run_key=resp.data["run_key"])
        # eager Celery executed the mock plan inside the request
        self.assertEqual(run.status in ("completed", "running"), True)

    def test_chat_continues_existing_conversation(self):
        self._auth()
        first = self.client.post("/api/v1/rental/chat/", {"message": "হ্যালো"})
        conv_id = first.data["conversation_id"]
        second = self.client.post(
            "/api/v1/rental/chat/",
            {"message": "আরেকটা রুম দেখাও"},
            HTTP_X_RENTORA_CONVERSATION=str(conv_id),
        )
        self.assertEqual(second.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(second.data["conversation_id"], conv_id)

    def test_chat_cannot_reach_another_users_conversation(self):
        self._auth(self.tenant)
        first = self.client.post("/api/v1/rental/chat/", {"message": "হ্যালো"})
        conv_id = first.data["conversation_id"]
        self._auth(self.other)
        resp = self.client.post(
            "/api/v1/rental/chat/",
            {"message": "হাই"},
            HTTP_X_RENTORA_CONVERSATION=str(conv_id),
        )
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_conversations_only_own(self):
        self._auth(self.other)
        first = self.client.post("/api/v1/rental/chat/", {"message": "হাই"})
        conv_id = first.data["conversation_id"]
        self._auth(self.tenant)
        resp = self.client.post(
            "/api/v1/rental/chat/",
            {"message": "হ্যালো"},
            HTTP_X_RENTORA_CONVERSATION=str(conv_id),
        )
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_conversation_detail_enriched_and_own_only(self):
        self._auth()
        first = self.client.post("/api/v1/rental/chat/", {"message": "রুম দেখাও"})
        conv_id = first.data["conversation_id"]
        detail = self.client.get(f"/api/v1/rental/conversations/{conv_id}/")
        self.assertEqual(detail.status_code, http_status.HTTP_200_OK)
        self.assertEqual(detail.data["agent"]["key"], AGENT_KEY)
        self.assertIn("messages", detail.data)
        self.assertIn("proposals", detail.data)
        self.assertIn("suggestions", detail.data)

        self._auth(self.other)
        other = self.client.get(f"/api/v1/rental/conversations/{conv_id}/")
        self.assertEqual(other.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_consent_approve_endpoint(self):
        self._auth()
        _, proposal = self.make_bookmark_proposal()
        resp = self.client.post(f"/api/v1/rental/proposals/{proposal.proposal_key}/approve/", {})
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "applied")
        self.assertTrue(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_consent_approve_forbidden_for_non_owner(self):
        _, proposal = self.make_bookmark_proposal()
        self._auth(self.other)
        resp = self.client.post(f"/api/v1/rental/proposals/{proposal.proposal_key}/approve/", {})
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")

    def test_consent_reject_endpoint(self):
        self._auth()
        _, proposal = self.make_bookmark_proposal()
        resp = self.client.post(
            f"/api/v1/rental/proposals/{proposal.proposal_key}/reject/",
            {"note": "দর বেশি"},
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "rejected")
        self.assertFalse(Wishlist.objects.filter(user=self.tenant, room=self.room).exists())

    def test_flag_off_blocks_chat(self):
        FeatureFlag.objects.filter(key=FLAG_KEY).update(status="disabled")
        invalidate_cache(FLAG_KEY)
        self._auth()
        resp = self.client.post("/api/v1/rental/chat/", {"message": "রুম দেখাও"})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error"], "feature_unavailable")

    def test_run_status_endpoint_own_only(self):
        self._auth()
        first = self.client.post("/api/v1/rental/chat/", {"message": "রুম দেখাও"})
        run_key = first.data["run_key"]
        detail = self.client.get(f"/api/v1/rental/runs/{run_key}/")
        self.assertEqual(detail.status_code, http_status.HTTP_200_OK)
        self.assertEqual(detail.data["run_key"], run_key)

        self._auth(self.other)
        other = self.client.get(f"/api/v1/rental/runs/{run_key}/")
        self.assertEqual(other.status_code, http_status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Seeding command
# ---------------------------------------------------------------------------


class SeedingCommandTests(TestCase):
    def setUp(self):
        enable_rental_feature()
        AgentToolRegistry.clear()

    def test_command_is_idempotent(self):
        call_command("register_rental_agent")
        call_command("register_rental_agent")  # no-op second time

        from ai_intelligence.models import AIPrompt, AIPromptVersion
        from feature_flags.models import FeatureFlag as Flag

        agent = get_agent(AGENT_KEY)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.status, "disabled")
        self.assertEqual(agent.audience, "users")
        self.assertEqual(agent.permission, "operator")
        self.assertCountEqual(agent.enabled_tools, ENABLED_TOOLS)
        self.assertTrue(Flag.objects.filter(key=FLAG_KEY).exists())
        prompt = AIPrompt.objects.get(prompt_key="rentora.rental_agent")
        active_versions = AIPromptVersion.objects.filter(prompt=prompt, is_active=True)
        self.assertTrue(active_versions.exists())
        # The agent stays disabled even after the command ran twice — nothing
        # becomes live by accident.
        self.assertTrue(Agent.objects.filter(key=AGENT_KEY, status="disabled").exists())
