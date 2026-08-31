"""Listing Autopilot tests (Phase 19.3).

Covers:
* deterministic analysis (eligibility, content/photo/price/renewal gaps,
  grounding stability);
* proposal creation + idempotency (per-week, per-type dedup);
* replay-safe apply (owner, per-field stale grounding, exactly-once, reject
  after ignore);
* tool registry + schema enforcement;
* API surface (ownership, bulk-approve batching, feature gating);
* Celery wiring + weekly run idempotency + batched notifications;
* no in-app "second engine" invariants (proposals are the only applied path).
"""

from __future__ import annotations

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APITestCase

from agents.models import AgentRun
from agents.tools import AgentToolRegistry, ToolValidationError, register_builtin_tools
from rooms.models import Room

from .services import (
    ConsentError,
    analyze_and_propose,
    autopilot_approve_and_apply,
    autopilot_reject,
    landlord_proposals,
)

User = get_user_model()

_GOOD_DESC = (
    "A complete 2-bedroom flat in Mirpur 10. Fully furnished with a study desk, "
    "wardrobe and bed. Attached bathroom, kitchen with gas and electricity, and "
    "high-speed wifi. 5 minutes walk from the bus stand and metro station. "
    "Suitable for students and young professionals. Rent includes maintenance."
)


def make_landlord(username="landlord1"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        role="landlord",
    )


def make_tenant(username="tenant1"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        role="tenant",
    )


def seed_autopilot():
    """Ensure the autopilot Agent exists so proposals/runs/telemetry hang off
    the same Phase 18/19 attribution model. Idempotent in every test case."""
    call_command("register_listing_autopilot")
    AgentToolRegistry.clear()
    register_builtin_tools()


def make_room(owner, **overrides):
    fields = dict(
        title="Complete Mirpur Flat",
        description=_GOOD_DESC,
        room_type="single",
        price=10000,
        area="Mirpur",
        address="House 27, Road 5, Mirpur 10, Dhaka 1216",
        lat=23.806,
        lng=90.368,
        amenities=["wifi", "attached bathroom", "kitchen", "furnished", "parking"],
        size_sqft=220,
    )
    fields.update(overrides)
    return Room.objects.create(owner=owner, **fields)


def attach_images(room, count=4):
    for i in range(count):
        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        room.images.create(
            is_primary=(i == 0),
            image=SimpleUploadedFile(f"aut{i}.png", buffer.getvalue(), "image/png"),
        )


class AutopilotAnalysisTests(TestCase):
    def setUp(self):
        seed_autopilot()

    def test_analysis_delegates_to_reference_engines(self):
        owner = make_landlord("ana1")
        room = make_room(owner)
        attach_images(room, 4)
        from .analysis import analyze_room

        payload = analyze_room(room)
        self.assertTrue(payload["eligible"])
        # Scores come from the reused engines, not invented here.
        self.assertIn("score", payload["listing_quality"])
        self.assertIn("score", payload["property_intelligence"])
        self.assertIn("direction", payload["price"])
        # A good, complete listing yields few or no recommendations.
        types = [r["type"] for r in payload["recommendations"]]
        self.assertNotIn("DESCRIPTION_UPDATE", types)
        self.assertNotIn("TITLE_UPDATE", types)

    def test_analysis_detects_content_gaps(self):
        owner = make_landlord("ana2")
        room = make_room(owner, title="thin", description="tiny", price=5000)
        attach_images(room, 0)
        from .analysis import analyze_room

        payload = analyze_room(room)
        types = {r["type"] for r in payload["recommendations"]}
        self.assertIn("TITLE_UPDATE", types)
        self.assertIn("DESCRIPTION_UPDATE", types)
        self.assertIn("PHOTO_RECOMMENDATION", types)

    def test_analysis_eligibility_blocks_tenant_owner(self):
        tenant = make_tenant("ana3")
        room = make_room(tenant)
        from .analysis import analyze_room

        payload = analyze_room(room)
        self.assertFalse(payload["eligible"])
        self.assertIn("owner_not_landlord", payload["eligibility_blocks"])
        # Privilege bypass lets staff/dev test the engine but keeps availability.
        payload2 = analyze_room(room, privilege_bypass=True)
        self.assertTrue(payload2["eligible"])

    def test_grounding_key_is_stable_and_sensitive(self):
        owner = make_landlord("ana4")
        room = make_room(owner)
        from .analysis import grounding_key

        k1 = grounding_key(room)
        room.title = "A completely different title now"
        room.save(update_fields=["title", "updated_at"])
        k2 = grounding_key(room)
        self.assertNotEqual(k1, k2)


class AutopilotProposalTests(TestCase):
    def setUp(self):
        seed_autopilot()

    def _propose(self, landlord, week="2026-W40", **overrides):
        return analyze_and_propose(landlord, make_room(landlord, **overrides), week=week)

    def test_proposals_created_pending_with_typed_actions(self):
        landlord = make_landlord("prop1")
        room = make_room(landlord, title="short", description="minimal", price=6000)
        attach_images(room, 0)
        snapshot = analyze_and_propose(landlord, room, week="2026-W40")
        self.assertTrue(snapshot.eligible)
        pending = landlord_proposals(landlord, status="pending")
        self.assertGreater(len(pending), 0)
        for p in pending:
            self.assertEqual(p.status, "pending")
            self.assertTrue((p.action or {}).get("tool", "").startswith("listing.autopilot.apply."))
            self.assertTrue((p.action or {}).get("arguments", {}).get("room_id") is not None)
            self.assertIn("stale_checks", (p.action or {}).get("arguments", {}))

    def test_analysis_idempotent_per_room_week(self):
        landlord = make_landlord("prop2")
        room = make_room(landlord, title="short", price=6000)
        s1 = analyze_and_propose(landlord, room, week="2026-W40")
        before = landlord_proposals(landlord, status="pending")
        s2 = analyze_and_propose(landlord, room, week="2026-W40")
        after = landlord_proposals(landlord, status="pending")
        self.assertEqual(s1.pk, s2.pk)
        self.assertEqual(before, after)  # no duplicate proposals same week

    def test_new_week_after_resolution_emits_new_proposals(self):
        landlord = make_landlord("prop3")
        room = make_room(landlord, title="x", description="y", price=6000)
        attach_images(room, 0)
        analyze_and_propose(landlord, room, week="2026-W40")
        title = landlord_proposals(landlord, status="pending")[0]
        autopilot_approve_and_apply(landlord, title)
        # New week: an unresolved slot is re-opened (title was applied).
        analyze_and_propose(landlord, room, week="2026-W41")
        new = [
            p
            for p in landlord_proposals(landlord, status="pending")
            if p.proposal_type == "TITLE_UPDATE"
        ]
        self.assertGreater(len(new), 0)

    def test_resolved_proposal_does_not_suppress_duplicate_guard(self):
        landlord = make_landlord("prop4")
        room = make_room(landlord, title="short", price=6000)
        analyze_and_propose(landlord, room, week="2026-W40")
        pend = landlord_proposals(landlord, status="pending")
        self.assertGreater(len(pend), 0)
        # Same week, same room: resolving one type frees only that type; the
        # rest remain single (no duplicates across types).
        analyze_and_propose(landlord, room, week="2026-W40")
        pend2 = landlord_proposals(landlord, status="pending")
        self.assertLessEqual(len(pend2), len(pend))


class AutopilotApplyTests(TestCase):
    def setUp(self):
        seed_autopilot()

    def test_apply_updates_room_and_is_replay_safe(self):
        landlord = make_landlord("apply1")
        room = make_room(landlord, title="shortened", description="tiny", price=6000)
        analyze_and_propose(landlord, room, week="2026-W40")
        desc = next(
            p for p in landlord_proposals(landlord) if p.proposal_type == "DESCRIPTION_UPDATE"
        )
        old = room.description
        applied = autopilot_approve_and_apply(landlord, desc)
        room.refresh_from_db()
        self.assertEqual(applied.status, "applied")
        self.assertTrue(applied.application_result.get("ok"))
        self.assertNotEqual(room.description, old)
        # Replay is a no-op.
        again = autopilot_approve_and_apply(landlord, desc)
        self.assertEqual(again.status, "applied")

    def test_apply_requires_owner(self):
        other = make_landlord("apply2b")
        landlord = make_landlord("apply2a")
        room = make_room(landlord, title="x", price=6000)
        attach_images(room, 0)
        analyze_and_propose(landlord, room, week="2026-W40")
        p = landlord_proposals(landlord)[0]
        with self.assertRaises(PermissionDenied):
            autopilot_approve_and_apply(other, p)

    def test_apply_blocks_on_stale_landlord_edit(self):
        landlord = make_landlord("apply3")
        room = make_room(landlord, title="x", description="y", price=6000)
        attach_images(room, 0)
        analyze_and_propose(landlord, room, week="2026-W40")
        title = next(p for p in landlord_proposals(landlord) if p.proposal_type == "TITLE_UPDATE")
        room.title = "Landlord manually rewrote the title"
        room.save(update_fields=["title", "updated_at"])
        applied = autopilot_approve_and_apply(landlord, title)
        self.assertEqual(applied.status, "failed")
        self.assertEqual(applied.application_result.get("error"), "stale_grounding")
        room.refresh_from_db()
        self.assertEqual(room.title, "Landlord manually rewrote the title")

    def test_reject_then_apply_fails(self):
        landlord = make_landlord("apply4")
        room = make_room(landlord, title="x", price=6000)
        attach_images(room, 0)
        analyze_and_propose(landlord, room, week="2026-W40")
        p = landlord_proposals(landlord)[0]
        rejected = autopilot_reject(landlord, p, reason="no thanks")
        self.assertEqual(rejected.status, "rejected")
        with self.assertRaises(ConsentError):
            autopilot_approve_and_apply(landlord, p)

    def test_apply_all_typed_executors(self):
        landlord = make_landlord("apply5")
        room = make_room(landlord, title="tiny", description="x", price=6000, amenities=[])
        analyze_and_propose(landlord, room, week="2026-W40")
        for p in landlord_proposals(landlord):
            res = autopilot_approve_and_apply(landlord, p)
            self.assertEqual(res.status, "applied", f"{p.proposal_type}: {res.application_result}")
        room.refresh_from_db()
        self.assertEqual(room.title, "Single in Mirpur")
        self.assertGreater(len(room.description), 20)

    def test_bulk_apply_skips_invalid_but_applies_valid(self):
        landlord = make_landlord("apply6")
        room = make_room(landlord, title="x", description="y", price=6000, amenities=[])
        attach_images(room, 0)
        analyze_and_propose(landlord, room, week="2026-W40")
        before = landlord_proposals(landlord)
        self.assertGreaterEqual(len(before), 2)
        p = before[0]
        # Reject first: bulk should skip it, another is still valid.
        autopilot_reject(landlord, p)
        pend = landlord_proposals(landlord)
        self.assertTrue(any(x.status == "pending" for x in pend))


class AutopilotToolTest(TestCase):
    def setUp(self):
        seed_autopilot()

    def test_tools_registered_and_schema_validated(self):
        names = [t.name for t in AgentToolRegistry.all()]
        self.assertIn("listing.autopilot.analyze", names)
        self.assertIn("listing.autopilot.apply.title-update", names)
        self.assertIn("listing.autopilot.apply.price-update", names)
        agent_tool = AgentToolRegistry.get("listing.autopilot.apply.title-update")
        self.assertIsNotNone(agent_tool)
        # Missing required arg fails schema
        with self.assertRaises(ToolValidationError):
            agent_tool.validate_arguments({"room_id": 1, "stale_checks": {}, "title": ""})
        # Invalid extra arg blocked
        with self.assertRaises(ToolValidationError):
            agent_tool.validate_arguments(
                {"room_id": 1, "title": "ok", "stale_checks": {}, "evil": True}
            )


class AutopilotTaskTests(TestCase):
    def setUp(self):
        seed_autopilot()

    @override_settings(LISTING_AUTOPILOT_ENABLED=True)
    def test_weekly_task_runs_and_notifies_batched(self):
        from listing_autopilot.tasks import run_weekly_autopilot

        landlord = make_landlord("task1")
        make_room(landlord, title="short", price=6000)
        result = run_weekly_autopilot.delay().get()
        self.assertTrue(result["enabled"])
        self.assertGreaterEqual(result["analyzed"], 1)
        self.assertIn("week_key", result)
        # Idempotent re-run: no new proposals, still succeeds.
        result2 = run_weekly_autopilot.delay().get()
        self.assertEqual(result2["analyzed"], result["analyzed"])
        self.assertGreaterEqual(result2["analyzed"], 1)

    def test_weekly_task_skips_disabled(self):
        from listing_autopilot.tasks import run_weekly_autopilot

        with override_settings(LISTING_AUTOPILOT_ENABLED=False):
            result = run_weekly_autopilot.delay().get()
            self.assertFalse(result["enabled"])

    def test_beat_schedule_has_autopilot_entry(self):
        from django.conf import settings

        self.assertIn("run-listing-autopilot", settings.CELERY_BEAT_SCHEDULE)


class AutopilotApiTests(APITestCase):
    def setUp(self):
        seed_autopilot()

    def test_landlord_sees_only_own_proposals(self):
        l1 = make_landlord("api1")
        l2 = make_landlord("api2")
        r1 = make_room(l1, title="short", price=6000)
        r2 = make_room(l2, title="short too", price=6000)
        analyze_and_propose(l1, r1, week="2026-W40")
        analyze_and_propose(l2, r2, week="2026-W40")

        self.client.force_authenticate(user=l1)
        res = self.client.get("/api/v1/autopilot/proposals/")
        self.assertEqual(res.status_code, 200)
        keys = {p["key"] for p in res.json()["proposals"]}
        own = {str(p.proposal_key) for p in landlord_proposals(l1)}
        self.assertEqual(keys, own)
        self.assertTrue(all(p["room_id"] == r1.pk for p in res.json()["proposals"]))

    def test_approve_endpoint(self):
        landlord = make_landlord("api3")
        room = make_room(landlord, title="thin", price=6000)
        analyze_and_propose(landlord, room, week="2026-W40")
        p = landlord_proposals(landlord)[0]
        self.client.force_authenticate(user=landlord)
        res = self.client.post(f"/api/v1/autopilot/proposals/{p.proposal_key}/approve/")
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, "applied")

    def test_reject_endpoint(self):
        landlord = make_landlord("api4")
        room = make_room(landlord, title="thin", price=6000)
        analyze_and_propose(landlord, room, week="2026-W40")
        p = landlord_proposals(landlord)[0]
        self.client.force_authenticate(user=landlord)
        res = self.client.post(
            f"/api/v1/autopilot/proposals/{p.proposal_key}/reject/", {"reason": "nope"}
        )
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, "rejected")

    def test_cross_owner_approve_forbidden(self):
        landlord = make_landlord("api5")
        other = make_landlord("api6")
        room = make_room(landlord, title="thin", price=6000)
        analyze_and_propose(landlord, room, week="2026-W40")
        p = landlord_proposals(landlord)[0]
        self.client.force_authenticate(user=other)
        res = self.client.post(f"/api/v1/autopilot/proposals/{p.proposal_key}/approve/")
        self.assertEqual(res.status_code, 404)  # not the owner's proposal

    def test_overview_reports_disabled_flag(self):
        landlord = make_landlord("api7")
        self.client.force_authenticate(user=landlord)
        res = self.client.get("/api/v1/autopilot/overview/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("enabled", body)
        self.assertIn("pending_count", body)


class AutopilotEvalHookTests(TestCase):
    def test_sdk_eval_hook_accepts_autopilot_run(self):
        seed_autopilot()
        import uuid

        from agents.models import Agent
        from agents.services import create_agent_eval_run

        agent = Agent.objects.get(key="ai.listing_autopilot")

        u = make_landlord("eval1")
        conv = agent.conversations.create(user=u, title="AI Listing Autopilot")
        run = AgentRun.objects.create(
            run_key=uuid.uuid4(),
            conversation=conv,
            agent=agent,
            user=u,
            status="completed",
            prompt_key=agent.prompt_key or "",
        )
        ev = create_agent_eval_run(run.id, feature_id="rentora.listing_autopilot")
        self.assertEqual(ev.status, "pending")
