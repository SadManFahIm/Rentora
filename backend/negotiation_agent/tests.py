"""Phase 19.4 — AI Negotiation Agent tests.

Covers:
* seeding command idempotency (feature + flag disabled + prompt + agent)
* model state machine legality + offer lifecycle
* tool registration + JSON schemas + capability tiers
* groundedness of ``negotiation.context`` / ``negotiation.history``
* full consent round-trips (draft → review → consent → send) through
  ``self_consent_approve`` / ``apply_proposal``:
    - create_offer / counter_offer / set_boundary / message.send / accept / finalize
    - idempotency + replay safety, conversation-owner-only consent, own-accept ban
* plain-user actions: offer reject/withdraw, negotiation reject/cancel
* expiry task (sent offers + dormant negotiations)
* API surface: auth, feature-off gating, ownership/RBAC on every endpoint
* anti-hallucination: no fabricated prices, peer constraints never leak
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APIClient

from agents.models import Agent, AgentProposal, AgentRun
from agents.services import create_conversation, create_proposal, create_run, register_agent
from agents.tools import (
    HIGH_RISK,
    READ_ONLY,
    RESULT_OK,
    STATE_CHANGING,
    AgentToolRegistry,
    register_builtin_tools,
)
from ai_intelligence.services import register_feature
from chat.models import ChatRoom, Message
from feature_flags.models import FeatureFlag, invalidate_cache
from notifications.models import Notification
from rooms.models import Room

from . import constants as C
from . import models as M
from . import services as S
from .models import Negotiation, NegotiationOffer

User = get_user_model()

FEATURE_ID = C.FEATURE_ID
AGENT_KEY = C.AGENT_KEY
ENABLED_TOOLS = [
    C.CONTEXT_TOOL,
    C.HISTORY_TOOL,
    C.SET_BOUNDARY_TOOL,
    C.CREATE_OFFER_TOOL,
    C.COUNTER_OFFER_TOOL,
    C.SEND_TOOL,
    C.ACCEPT_TOOL,
    C.FINALIZE_TOOL,
    "room.by_id",
    "price.compare",
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


def enable_negotiation_feature():
    register_feature(
        feature_id=FEATURE_ID,
        name="AI Negotiation Agent",
        category="agent",
        is_enabled=True,
        feature_flag_key=C.FLAG_KEY,
        default_provider="mock_llm",
    )
    FeatureFlag.objects.update_or_create(
        key=C.FLAG_KEY,
        defaults={"status": "enabled", "rollout_percentage": 100},
    )
    invalidate_cache(C.FLAG_KEY)


def make_agent(**overrides):
    defaults = dict(
        key=AGENT_KEY,
        name="Rentora AI Negotiation Agent",
        status="active",
        audience="users",
        permission="admin",  # HIGH_RISK ceiling so accept/finalize can be *requested*
        feature_id=FEATURE_ID,
        prompt_key="",
        provider="mock_llm",
        system_instructions=(
            "You are the negotiation assistant. Only answer grounded in tool "
            "results. Never invent prices or the other side's intent; every "
            "action needs explicit in-chat user approval."
        ),
        enabled_tools=ENABLED_TOOLS,
    )
    defaults.update(overrides)
    return register_agent(**defaults)


@MOCK_SETTINGS
class NegotiationTestCase(TestCase):
    def setUp(self):
        self.tenant = make_user("tenant")
        self.landlord = make_user("landlord")
        self.other = make_user("other")
        enable_negotiation_feature()
        AgentToolRegistry.clear()
        register_builtin_tools()
        self.room = make_room(self.landlord)
        self.agent = make_agent()

    def tearDown(self):
        AgentToolRegistry.clear()

    def make_conversation(self, user=None, negotiation=None):
        conv = create_conversation(
            self.agent, user or self.tenant, title="Negotiation", metadata={}
        )
        if negotiation is not None:
            S.bind_conversation(negotiation, conv, user or self.tenant)
        return conv

    def make_negotiation(self, tenant=None, landlord=None, **overrides):
        negotiation, _created = S.get_or_create_negotiation(
            room=self.room,
            tenant=tenant or self.tenant,
            landlord=landlord or self.landlord,
        )
        return negotiation

    def make_proposal(
        self, tool_name, arguments, *, conversation=None, actor=None, approval="any_staff"
    ):
        conv = conversation or self.make_conversation(actor or self.tenant)
        run, _ = create_run(conv, "দর করো", actor=actor or self.tenant)
        tool = AgentToolRegistry.get(tool_name)
        return run, create_proposal(
            run,
            tool,
            arguments,
            f"call-{tool_name.replace('.', '-')}-1",
            approval_required=approval,
            actor=actor or self.tenant,
        )

    def draft_and_send(self, *, amount=9000, kind="offer", message="দর ৯০০০ মেনে নেবেন?"):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "amount": amount,
                "message": message,
            },
            conversation=conv,
            actor=self.tenant,
        )
        applied = S.self_consent_approve(self.tenant, proposal)
        self.assertEqual(applied.status, "applied")
        offer = NegotiationOffer.objects.get(kind=kind)
        _, send_proposal = self.make_proposal(
            C.SEND_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=conv,
            actor=self.tenant,
        )
        applied_send = S.self_consent_approve(self.tenant, send_proposal)
        self.assertEqual(applied_send.status, "applied")
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.SENT)
        negotiation.refresh_from_db()
        return negotiation, offer


# ---------------------------------------------------------------------------
# Seeding command
# ---------------------------------------------------------------------------


class SeedingCommandTests(TestCase):
    def setUp(self):
        enable_negotiation_feature()
        AgentToolRegistry.clear()
        register_builtin_tools()

    def test_command_is_idempotent_and_stays_live_off(self):
        call_command("register_negotiation_agent")
        call_command("register_negotiation_agent")  # no-op second run

        from ai_intelligence.models import AIPrompt, AIPromptVersion

        agent = Agent.objects.get(key=AGENT_KEY)
        self.assertEqual(agent.status, "disabled")  # never live by accident
        self.assertEqual(agent.audience, "users")
        self.assertEqual(agent.permission, "admin")
        self.assertCountEqual(agent.enabled_tools, ENABLED_TOOLS)
        self.assertTrue(FeatureFlag.objects.filter(key=C.FLAG_KEY, status="disabled").exists())
        prompt = AIPrompt.objects.get(prompt_key=C.PROMPT_KEY)
        active = AIPromptVersion.objects.get(prompt=prompt, is_active=True)
        self.assertTrue(active)
        # No Phase 19.5 leakage: the seeded prompt is purely the negotiation one.
        self.assertNotIn("Voice", active.template)
        self.assertIn("ABSOLUTE GROUNDING RULES", active.template)


# ---------------------------------------------------------------------------
# State machine + offers
# ---------------------------------------------------------------------------


class StateMachineTests(TestCase):
    def setUp(self):
        self.tenant = make_user("tenant")
        self.landlord = make_user("landlord")
        self.room = make_room(self.landlord)
        self.negotiation = Negotiation.objects.create(
            room=self.room,
            tenant=self.tenant,
            landlord=self.landlord,
            expires_at=timezone.now() + timedelta(days=30),
        )

    def test_legal_routes(self):
        self.assertEqual(self.negotiation.status, M.NegotiationStatus.INITIATED)
        self.assertTrue(M.transition_negotiation(self.negotiation, M.NegotiationStatus.ACTIVE))
        self.assertEqual(self.negotiation.status, M.NegotiationStatus.ACTIVE)

    def test_illegal_move_never_executes(self):
        self.negotiation.status = M.NegotiationStatus.ACCEPTED
        self.negotiation.save(update_fields=["status"])
        changed = M.transition_negotiation(self.negotiation, M.NegotiationStatus.ACTIVE)
        self.assertFalse(changed)
        self.negotiation.refresh_from_db()
        self.assertEqual(self.negotiation.status, M.NegotiationStatus.ACCEPTED)
        self.assertEqual(
            M.transition_negotiation(self.negotiation, M.NegotiationStatus.CLOSED), True
        )

    def test_terminal_states_are_immutable(self):
        for status in (
            M.NegotiationStatus.REJECTED,
            M.NegotiationStatus.EXPIRED,
            M.NegotiationStatus.CANCELLED,
            M.NegotiationStatus.CLOSED,
        ):
            negotiation = Negotiation.objects.create(
                room=make_room(self.landlord),
                tenant=self.tenant,
                landlord=self.landlord,
                status=status,
                expires_at=timezone.now() + timedelta(days=30),
            )
            self.assertFalse(M.transition_negotiation(negotiation, M.NegotiationStatus.ACTIVE))
            negotiation.refresh_from_db()
            self.assertEqual(negotiation.status, status)

    def test_invites_timeline_labels(self):
        M.record_event(self.negotiation, "created", actor=self.tenant)
        self.assertTrue(self.negotiation.events.filter(event_type="created").exists())


# ---------------------------------------------------------------------------
# Tool registration / schema
# ---------------------------------------------------------------------------


class ToolRegistrationTests(NegotiationTestCase):
    def test_all_eight_tools_registered(self):
        for name in ENABLED_TOOLS[:8]:
            tool = AgentToolRegistry.get(name)
            self.assertIsNotNone(tool, name)

    def test_capability_tiers(self):
        self.assertEqual(AgentToolRegistry.get(C.CONTEXT_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(C.HISTORY_TOOL).capability, READ_ONLY)
        self.assertEqual(AgentToolRegistry.get(C.SET_BOUNDARY_TOOL).capability, STATE_CHANGING)
        self.assertEqual(AgentToolRegistry.get(C.CREATE_OFFER_TOOL).capability, STATE_CHANGING)
        self.assertEqual(AgentToolRegistry.get(C.COUNTER_OFFER_TOOL).capability, STATE_CHANGING)
        self.assertEqual(AgentToolRegistry.get(C.SEND_TOOL).capability, STATE_CHANGING)
        self.assertEqual(AgentToolRegistry.get(C.ACCEPT_TOOL).capability, HIGH_RISK)
        self.assertEqual(AgentToolRegistry.get(C.FINALIZE_TOOL).capability, HIGH_RISK)

    def test_schemas_validate(self):
        from agents.tools import ToolValidationError

        context = AgentToolRegistry.get(C.CONTEXT_TOOL)
        context.validate_arguments({"negotiation_key": "00000000-0000-0000-0000-000000000001"})
        with self.assertRaises(ToolValidationError):
            context.validate_arguments({})  # key required

        offer = AgentToolRegistry.get(C.CREATE_OFFER_TOOL)
        offer.validate_arguments(
            {"negotiation_key": "00000000-0000-0000-0000-000000000001", "amount": 9000}
        )
        with self.assertRaises(ToolValidationError):
            offer.validate_arguments({"negotiation_key": "x", "amount": -5})
        with self.assertRaises(ToolValidationError):
            offer.validate_arguments({"amount": 9000})  # no key

        # The executor must never accept a user argument — owner comes from the
        # server context, so cross-account drafts are impossible.
        with self.assertRaises(ToolValidationError):
            offer.validate_arguments(
                {
                    "negotiation_key": "00000000-0000-0000-0000-000000000001",
                    "amount": 9000,
                    "user_id": self.other.pk,
                }
            )


# ---------------------------------------------------------------------------
# Grounded reads
# ---------------------------------------------------------------------------


class ContextToolTests(NegotiationTestCase):
    def test_context_is_grounded_and_leaks_nothing_private(self):
        negotiation = self.make_negotiation()
        S.set_constraints(negotiation, self.tenant, {"max_budget": "9500"})
        S.set_constraints(negotiation, self.landlord, {"min_rent": "12000"})

        tool = AgentToolRegistry.get(C.CONTEXT_TOOL)
        outcome = tool.execute(
            {"negotiation_key": str(negotiation.negotiation_key)},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        data = outcome["data"]
        self.assertEqual(data["room"]["id"], self.room.pk)
        self.assertEqual(data["my_role"], "tenant")
        # Own constraints visible; the counterparty's private ones are NOT.
        self.assertEqual(data["my_constraints"]["max_budget"], "9500")
        self.assertNotIn("min_rent", str(data.get("peer_constraints_set")))
        self.assertTrue(data["peer_constraints_set"] is True)

    def test_non_participant_cannot_read_context(self):
        negotiation = self.make_negotiation()
        tool = AgentToolRegistry.get(C.CONTEXT_TOOL)
        outcome = tool.execute(
            {"negotiation_key": str(negotiation.negotiation_key)},
            {"user": self.other},
        )
        self.assertFalse(outcome[RESULT_OK])
        self.assertEqual(outcome["error"], "negotiation_not_found")

    def test_history_is_auditable_timeline(self):
        negotiation = self.make_negotiation()
        tool = AgentToolRegistry.get(C.HISTORY_TOOL)
        outcome = tool.execute(
            {"negotiation_key": str(negotiation.negotiation_key)},
            {"user": self.tenant},
        )
        self.assertTrue(outcome[RESULT_OK])
        self.assertEqual(outcome["data"]["status"], "initiated")
        self.assertTrue(any(e["event"] == "created" for e in outcome["data"]["events"]))


# ---------------------------------------------------------------------------
# Consent round-trips
# ---------------------------------------------------------------------------


class ConsentFlowTests(NegotiationTestCase):
    def test_set_boundary_consent_applies_own_bounds(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, proposal = self.make_proposal(
            C.SET_BOUNDARY_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "boundary": {"max_budget": "9500", "other_notes": "২ ভাই"},
            },
            conversation=conv,
            actor=self.tenant,
        )
        applied = S.self_consent_approve(self.tenant, proposal)
        self.assertEqual(applied.status, "applied")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.tenant_constraints["max_budget"], "9500")
        # The landlord's side stays untouched.
        self.assertEqual(negotiation.landlord_constraints, {})

    def test_draft_then_send_two_step_consent(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, draft_proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "amount": 9000,
                "message": "দর ৯০০০ মেনে নেবেন?",
            },
            conversation=conv,
            actor=self.tenant,
        )
        applied = S.self_consent_approve(self.tenant, draft_proposal)
        self.assertEqual(applied.status, "applied")
        offer = NegotiationOffer.objects.get()
        self.assertEqual(offer.status, M.OfferStatus.DRAFT)  # write != send
        self.assertFalse(Message.objects.exists())
        self.assertEqual(negotiation.status, M.NegotiationStatus.INITIATED)

        _, send_proposal = self.make_proposal(
            C.SEND_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=conv,
            actor=self.tenant,
        )
        applied_send = S.self_consent_approve(self.tenant, send_proposal)
        self.assertEqual(applied_send.status, "applied")
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.SENT)
        self.assertIsNotNone(offer.chat_message)
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.OFFER_PENDING)
        # The chat thread is the real tenant↔landlord DIRECT room, delivered as
        # a TEXT message from the tenant.
        chat_room = negotiation.chat_room
        self.assertEqual(chat_room.room_type, ChatRoom.RoomType.DIRECT)
        msg = Message.objects.get(pk=offer.chat_message_id)
        self.assertEqual(msg.sender_id, self.tenant.pk)
        self.assertEqual(msg.message_type, Message.MessageType.TEXT)
        self.assertIn("৯০০০", msg.content)
        self.assertTrue(Notification.objects.filter(title__contains="offer").exists())

    def test_counter_offer_consent(self):
        negotiation, _offer = self.draft_and_send()
        # Landlord replies with a counter via their own conversation.
        conv = self.make_conversation(self.landlord, negotiation)
        _, proposal = self.make_proposal(
            C.COUNTER_OFFER_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key), "amount": 11000},
            conversation=conv,
            actor=self.landlord,
        )
        applied = S.self_consent_approve(self.landlord, proposal)
        self.assertEqual(applied.status, "applied")
        counter = NegotiationOffer.objects.get(kind="counter")
        self.assertEqual(counter.status, M.OfferStatus.DRAFT)

    def test_accept_requires_unexpired_sent_offer_and_peer(self):
        negotiation, offer = self.draft_and_send()
        conv = self.make_conversation(self.landlord, negotiation)
        _, accept_proposal = self.make_proposal(
            C.ACCEPT_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=conv,
            actor=self.landlord,
        )
        applied = S.self_consent_approve(self.landlord, accept_proposal)
        self.assertEqual(applied.status, "applied")
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.ACCEPTED)
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.ACCEPTED)

    def test_accept_proposal_owned_by_sender_is_refused(self):
        """The SENDER's own agent can never mark their offer accepted."""
        negotiation, offer = self.draft_and_send()
        _, accept_proposal = self.make_proposal(
            C.ACCEPT_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=self.make_conversation(self.tenant, negotiation),
            actor=self.tenant,
        )
        applied = S.self_consent_approve(self.tenant, accept_proposal)
        self.assertEqual(applied.status, "failed")
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.SENT)

    def test_finalize_handoff_never_books(self):
        negotiation, offer = self.draft_and_send()
        conv = self.make_conversation(self.landlord, negotiation)
        _, accept_proposal = self.make_proposal(
            C.ACCEPT_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=conv,
            actor=self.landlord,
        )
        S.self_consent_approve(self.landlord, accept_proposal)

        _, finalize_proposal = self.make_proposal(
            C.FINALIZE_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key)},
            conversation=conv,
            actor=self.landlord,
        )
        applied = S.self_consent_approve(self.landlord, finalize_proposal)
        self.assertEqual(applied.status, "applied")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.CLOSED)
        # Room unchanged, no booking/payment created anywhere.
        self.room.refresh_from_db()
        self.assertEqual(self.room.price, 10000)
        self.assertTrue(self.room.is_available)
        self.assertTrue(Notification.objects.filter(title__contains="closed").exists())

    def test_finalize_only_from_accepted(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, proposal = self.make_proposal(
            C.FINALIZE_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key)},
            conversation=conv,
            actor=self.tenant,
        )
        applied = S.self_consent_approve(self.tenant, proposal)
        applied.refresh_from_db()
        self.assertEqual(applied.status, "failed")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.INITIATED)

    def test_consent_is_replay_safe_and_owner_only(self):
        negotiation, offer = self.draft_and_send()
        from django.core.exceptions import PermissionDenied

        conv = self.make_conversation(self.landlord, negotiation)
        _, accept_proposal = self.make_proposal(
            C.ACCEPT_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "offer_key": str(offer.offer_key),
            },
            conversation=conv,
            actor=self.landlord,
        )
        # Only the conversation owner may consent.
        with self.assertRaises(PermissionDenied):
            S.self_consent_approve(self.tenant, accept_proposal)
        accept_proposal.refresh_from_db()
        self.assertEqual(accept_proposal.status, "pending")

        applied = S.self_consent_approve(self.landlord, accept_proposal)
        replay = S.self_consent_approve(self.landlord, applied)
        self.assertEqual(replay.status, "applied")
        self.assertEqual(NegotiationOffer.objects.count(), 1)  # no duplicate side-effects

    def test_reject_proposal_is_terminal(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key), "amount": 9000},
            conversation=conv,
            actor=self.tenant,
        )
        rejected = S.self_reject(self.tenant, proposal, reason="আর দরকার নেই")
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.reviewed_by, self.tenant)
        self.assertIn("আর দরকার নেই", rejected.rejection_reason)
        from .services import NegotiationConsentError

        with self.assertRaises(NegotiationConsentError):
            S.self_consent_approve(self.tenant, rejected)

    def test_consent_never_bypasses_participant_boundary(self):
        """A proposal targeting someone else's negotiation cannot self-consent."""
        other_neg = Negotiation.objects.create(
            room=self.room,
            tenant=self.other,
            landlord=self.landlord,
            expires_at=timezone.now() + timedelta(days=30),
        )
        conv = self.make_conversation(self.tenant, self.make_negotiation())
        _, proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {"negotiation_key": str(other_neg.negotiation_key), "amount": 9000},
            conversation=conv,
            actor=self.tenant,
        )
        from .services import NegotiationConsentError

        with self.assertRaises(NegotiationConsentError):
            S.self_consent_approve(self.tenant, proposal)


# ---------------------------------------------------------------------------
# Plain-user offer/negotiation actions
# ---------------------------------------------------------------------------


class UserActionTests(NegotiationTestCase):
    def test_counterparty_rejects_sent_offer(self):
        negotiation, offer = self.draft_and_send()
        result = S.reject_offer(negotiation, self.landlord, offer, reason="দাম বেশি")
        self.assertEqual(result["ok"], "offer_rejected")
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.REJECTED)
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.ACTIVE)  # fell back to open

    def test_sender_withdraws_own_offer(self):
        negotiation, offer = self.draft_and_send()
        result = S.reject_offer(negotiation, self.tenant, offer)
        offer.refresh_from_db()
        self.assertEqual(result["ok"], "offer_withdrawn")
        self.assertEqual(offer.status, M.OfferStatus.WITHDRAWN)

    def test_withdraw_from_draft_is_refused(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        _, proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key), "amount": 9000},
            conversation=conv,
            actor=self.tenant,
        )
        S.self_consent_approve(self.tenant, proposal)
        offer = NegotiationOffer.objects.get()
        with self.assertRaises(S.NegotiationError):
            S.reject_offer(negotiation, self.tenant, offer)  # draft_not_sent

    def test_outsider_cannot_action_an_offer(self):
        negotiation, offer = self.draft_and_send()
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            S.reject_offer(negotiation, self.other, offer)

    def test_reject_negotiation_terminal(self):
        negotiation = self.make_negotiation()
        result = S.reject_negotiation(negotiation, self.tenant, reason="মানেনি")
        self.assertEqual(result["ok"], "negotiation_rejected")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.REJECTED)
        with self.assertRaises(S.NegotiationError):
            S.reject_negotiation(negotiation, self.landlord)

    def test_cancel_negotiation_terminal(self):
        negotiation = self.make_negotiation()
        result = S.cancel_negotiation(negotiation, self.landlord)
        self.assertEqual(result["ok"], "negotiation_cancelled")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.CANCELLED)

    def test_outsider_cannot_reject_negotiation(self):
        negotiation = self.make_negotiation()
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            S.reject_negotiation(negotiation, self.other)


# ---------------------------------------------------------------------------
# Expiry + stale protection
# ---------------------------------------------------------------------------


class ExpiryTests(NegotiationTestCase):
    def test_expire_sent_offers_and_dormant_negotiations(self):
        _negotiation, offer = self.draft_and_send()
        NegotiationOffer.objects.filter(pk=offer.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        other_neg = Negotiation.objects.create(
            room=make_room(self.landlord),
            tenant=self.tenant,
            landlord=self.landlord,
            status="active",
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        dry = S.expire_negotiations(dry_run=True)
        self.assertEqual(dry["offers_expired"], 1)
        self.assertEqual(dry["negotiations_expired"], 1)

        result = S.expire_negotiations()
        self.assertEqual(result["offers_expired"], 1)
        self.assertEqual(result["negotiations_expired"], 1)
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.EXPIRED)
        other_neg.refresh_from_db()
        self.assertEqual(other_neg.status, M.NegotiationStatus.EXPIRED)

        # Idempotent second run.
        self.assertEqual(S.expire_negotiations(), {"offers_expired": 0, "negotiations_expired": 0})

    def test_stale_negotiation_blocks_new_writes(self):
        negotiation = self.make_negotiation()
        negotiation.status = M.NegotiationStatus.REJECTED
        negotiation.save(update_fields=["status"])
        with self.assertRaises(S.NegotiationError) as ctx:
            S.draft_offer(negotiation, self.tenant, amount=9000)
        self.assertEqual(ctx.exception.args[0], "negotiation_stale")

    def test_open_offer_cap_prevents_spam(self):
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        for i in range(5):
            _, proposal = self.make_proposal(
                C.CREATE_OFFER_TOOL,
                {"negotiation_key": str(negotiation.negotiation_key), "amount": 8500 + i},
                conversation=conv,
                actor=self.tenant,
            )
            S.self_consent_approve(self.tenant, proposal)
        with self.assertRaises(S.NegotiationError) as ctx:
            S.draft_offer(negotiation, self.tenant, amount=9600)
        self.assertEqual(ctx.exception.args[0], "too_many_open_offers")

    def test_feature_disabled_no_ops_detected(self):
        with override_settings(NEGOTIATION_AGENT_ENABLED=False):
            negotiation = self.make_negotiation()
            with self.assertRaises(S.NegotiationError) as ctx:
                S.draft_offer(negotiation, self.tenant, amount=9000)
            self.assertEqual(ctx.exception.args[0], "feature_disabled")


# ---------------------------------------------------------------------------
# Unique negotiation creation
# ---------------------------------------------------------------------------


class CreationTests(NegotiationTestCase):
    def test_unique_per_room_tenant_landlord(self):
        first, created1 = S.get_or_create_negotiation(
            room=self.room, tenant=self.tenant, landlord=self.landlord
        )
        second, created2 = S.get_or_create_negotiation(
            room=self.room, tenant=self.tenant, landlord=self.landlord
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first.pk, second.pk)

    def test_unique_constraint_at_db_level(self):
        S.get_or_create_negotiation(room=self.room, tenant=self.tenant, landlord=self.landlord)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Negotiation.objects.create(
                room=self.room,
                tenant=self.tenant,
                landlord=self.landlord,
                expires_at=timezone.now() + timedelta(days=30),
            )


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


class ApiTests(NegotiationTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.tenant)

    def test_chat_requires_authentication(self):
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_chat_starts_negotiation_for_tenant(self):
        self._auth()
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        negotiation = Negotiation.objects.get(
            room=self.room, tenant=self.tenant, landlord=self.landlord
        )
        self.assertIsNotNone(negotiation)
        self.assertIsNotNone(negotiation.tenant_conversation_id)
        run = AgentRun.objects.get(run_key=resp.data["run_key"])
        self.assertEqual(run.status in ("completed", "running"), True)

    def test_landlord_needs_existing_negotiation(self):
        self._auth(self.landlord)
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error"], "landlord_needs_existing_negotiation")

    def test_landlord_responds_to_tenants_negotiation(self):
        self.make_negotiation()  # tenant already initiated
        self._auth(self.landlord)
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)
        negotiation = Negotiation.objects.get(room=self.room)
        self.assertIsNotNone(negotiation.landlord_conversation_id)

    def test_chat_requires_room_to_start(self):
        self._auth()
        resp = self.client.post("/api/v1/negotiation/chat/", {"message": "দর করো"})
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_room_owner_cannot_start_a_negotiation_against_themselves(self):
        # The owner path is covered by ``test_landlord_needs_existing_negotiation``
        # + ``test_landlord_responds_to_tenants_negotiation`` — the owner can
        # never initiate against themselves (400 without an existing thread).
        self._auth(self.landlord)
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error"], "landlord_needs_existing_negotiation")

    def test_flag_off_blocks_chat_before_side_effects(self):
        FeatureFlag.objects.filter(key=C.FLAG_KEY).update(status="disabled")
        invalidate_cache(C.FLAG_KEY)
        self._auth()
        resp = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["error"], "feature_unavailable")
        self.assertFalse(Negotiation.objects.exists())

    def test_conversation_detail_own_only(self):
        self._auth()
        first = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        conv_id = first.data["conversation_id"]
        detail = self.client.get(f"/api/v1/negotiation/conversations/{conv_id}/")
        self.assertEqual(detail.status_code, http_status.HTTP_200_OK)
        self.assertEqual(detail.data["agent"]["key"], AGENT_KEY)
        self.assertIn("negotiation", detail.data)
        self.assertIsNotNone(detail.data["negotiation"]["key"])

        self._auth(self.other)
        other = self.client.get(f"/api/v1/negotiation/conversations/{conv_id}/")
        self.assertEqual(other.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_conversation_list_only_own(self):
        self._auth()
        self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        self._auth(self.other)
        resp = self.client.get("/api/v1/negotiation/conversations/")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_negotiations_list_only_participants(self):
        negotiation = self.make_negotiation()
        self._auth(self.tenant)
        rows = self.client.get("/api/v1/negotiation/negotiations/").data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], str(negotiation.negotiation_key))

        self._auth(self.other)
        rows = self.client.get("/api/v1/negotiation/negotiations/").data
        self.assertEqual(rows, [])

    def test_negotiation_detail_participant_only(self):
        negotiation = self.make_negotiation()
        self._auth(self.landlord)
        resp = self.client.get(f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/")
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data["my_role"], "landlord")
        self.assertIn("offers", resp.data)
        self.assertIn("timeline", resp.data)

        self._auth(self.other)
        resp = self.client.get(f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/")
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_consent_approve_endpoint(self):
        negotiation = self.make_negotiation()
        self._auth()
        _, proposal = self.make_proposal(
            C.SET_BOUNDARY_TOOL,
            {
                "negotiation_key": str(negotiation.negotiation_key),
                "boundary": {"max_budget": "9000"},
            },
            conversation=self.make_conversation(self.tenant, negotiation),
            actor=self.tenant,
        )
        resp = self.client.post(
            f"/api/v1/negotiation/proposals/{proposal.proposal_key}/approve/", {}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "applied")
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.tenant_constraints["max_budget"], "9000")

    def test_consent_reject_endpoint(self):
        negotiation = self.make_negotiation()
        self._auth()
        _, proposal = self.make_proposal(
            C.CREATE_OFFER_TOOL,
            {"negotiation_key": str(negotiation.negotiation_key), "amount": 9000},
            conversation=self.make_conversation(self.tenant, negotiation),
            actor=self.tenant,
        )
        resp = self.client.post(
            f"/api/v1/negotiation/proposals/{proposal.proposal_key}/reject/",
            {"note": "পরে করব"},
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "rejected")

    def test_offer_reject_endpoint(self):
        negotiation, offer = self.draft_and_send()
        self._auth(self.landlord)
        resp = self.client.post(
            f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/"
            f"offers/{offer.offer_key}/reject/",
            {"note": "দাম বেশি"},
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.REJECTED)

    def test_offer_reject_scoped_to_participants(self):
        negotiation, offer = self.draft_and_send()
        self._auth(self.other)
        resp = self.client.post(
            f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/"
            f"offers/{offer.offer_key}/reject/",
            {},
        )
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)
        offer.refresh_from_db()
        self.assertEqual(offer.status, M.OfferStatus.SENT)

    def test_negotiation_reject_and_cancel_endpoints(self):
        negotiation = self.make_negotiation()
        self._auth(self.tenant)
        resp = self.client.post(
            f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/reject/", {}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        negotiation.refresh_from_db()
        self.assertEqual(negotiation.status, M.NegotiationStatus.REJECTED)

        other_neg = self.make_negotiation(tenant=self.other)
        self._auth(self.other)
        resp = self.client.post(
            f"/api/v1/negotiation/negotiations/{other_neg.negotiation_key}/cancel/", {}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        other_neg.refresh_from_db()
        self.assertEqual(other_neg.status, M.NegotiationStatus.CANCELLED)

    def test_negotiation_actions_outsider_forbidden(self):
        negotiation = self.make_negotiation()
        self._auth(self.other)
        resp = self.client.post(
            f"/api/v1/negotiation/negotiations/{negotiation.negotiation_key}/cancel/", {}
        )
        self.assertEqual(resp.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_run_status_own_only(self):
        self._auth()
        first = self.client.post(
            "/api/v1/negotiation/chat/", {"message": "দর করো", "room_id": self.room.pk}
        )
        run_key = first.data["run_key"]
        detail = self.client.get(f"/api/v1/negotiation/runs/{run_key}/")
        self.assertEqual(detail.status_code, http_status.HTTP_200_OK)
        self.assertEqual(detail.data["run_key"], run_key)

        self._auth(self.other)
        other = self.client.get(f"/api/v1/negotiation/runs/{run_key}/")
        self.assertEqual(other.status_code, http_status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Anti-hallucination at the session level (mock plan that would try to cheat)
# ---------------------------------------------------------------------------


class HallucinationGuardTests(NegotiationTestCase):
    def test_session_never_auto_applies_offers(self):
        """A chat run can request ``negotiation.create_offer`` but nothing is
        written until the in-chat consent applies the proposal — never an
        auto-send, never an auto-apply."""
        negotiation = self.make_negotiation()
        conv = self.make_conversation(self.tenant, negotiation)
        run, _ = create_run(conv, "৯০০০ অফার করে পাঠাও", actor=self.tenant)
        run.metadata["mock_plan"] = [
            {
                "type": "tool_call",
                "name": C.CREATE_OFFER_TOOL,
                "arguments": {"negotiation_key": str(negotiation.negotiation_key), "amount": 9000},
            },
            {"type": "text", "content": "অফার তৈরি হয়েছে — অনুমোদন দিলে পাঠাব।"},
        ]
        run.save(update_fields=["metadata"])
        from agents.session import AgentSession

        AgentSession(conv, actor=self.tenant).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        # The state-changing call only created a PENDING proposal.
        proposal = AgentProposal.objects.get(proposal_type=C.CREATE_OFFER_TOOL)
        self.assertEqual(proposal.status, "pending")
        # No DRAFT, no SENT, no chat message: consent must come before ANY write.
        self.assertEqual(NegotiationOffer.objects.count(), 0)
        self.assertFalse(Message.objects.exists())
        self.assertTrue(
            proposal.action["arguments"]["negotiation_key"] == str(negotiation.negotiation_key)
        )
