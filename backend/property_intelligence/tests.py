"""Phase 19.1 — Property Intelligence Score tests.

Covers: scoring rules (bounds, weights, redistribution, confidence, version),
price/location/photo/trust/demand signals, cache + invalidation, public & staff
API, serializer badge, the READ_ONLY agent tool (grounded + audited), and
listing-quality regression compatibility.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from rest_framework.test import APITestCase

from fraud.models import FraudReport, FraudSignal
from pricing.models import MarketStat
from rooms.models import Room, RoomImage

from . import scoring
from .scoring import SCORE_VERSION

User = get_user_model()

_GOOD_DESCRIPTION = (
    "A complete 2-bedroom flat in Mirpur 10. Fully furnished with a study "
    "desk, wardrobe and bed. Attached bathroom, kitchen with gas and "
    "electricity, and high-speed wifi. 5 minutes walk from Mirpur 10 bus "
    "stand and the metro station. Suitable for students and young "
    "professionals. Monthly rent includes maintenance. Immediate move-in."
)


def make_user(username="pi_owner"):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345"
    )


def make_room(owner, **overrides):
    fields = dict(
        title="Complete Mirpur Flat",
        description=_GOOD_DESCRIPTION,
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
    from io import BytesIO

    from PIL import Image

    for i in range(count):
        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        RoomImage.objects.create(
            room=room,
            is_primary=(i == 0),
            image=SimpleUploadedFile(f"pi{i}.png", buffer.getvalue(), "image/png"),
        )


def make_market(area="Mirpur", room_type="single", avg=10000, sample=10):
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


# ---------------------------------------------------------------------------
# Pure scoring rules
# ---------------------------------------------------------------------------


def _full_data(**overrides):
    """A data dict where every component is available and scores reasonably."""
    data = {
        "listing_quality": {"score": 90, "available": True, "level": "good"},
        "price": {
            "available": True,
            "classification": "fair_price",
            "message": "Priced close to the market average (2.0%).",
            "sample_size": 12,
        },
        "location": {"available": True, "metro_score": 82},
        "photos": {
            "count": 4,
            "has_primary": True,
            "anomalies": [],
            "moderation_risk": 0,
            "gps_consistent": True,
        },
        "trust": {
            "verified": True,
            "nid_verified": True,
            "tenant_verified": True,
            "fraud": {"exists": True, "severity": "clean"},
        },
        "demand": {
            "own": {"views": 10, "saves": 2, "requests": 1},
            "area": {"score": 60, "total_signals": 40},
        },
        "quality_suggestions": [],
        "stale_days": 5,
        "stale_threshold_days": 90,
    }
    data.update(overrides)
    return data


class ScoringRuleTests(TestCase):
    def test_all_available_respects_weights_and_stays_0_100(self):
        result = scoring.compute_property_intelligence(_full_data())
        self.assertEqual(result["score_version"], SCORE_VERSION)
        self.assertIn(result["score"], range(0, 101))
        for meta in result["breakdown"].values():
            self.assertEqual(meta["availability"], "available")
            self.assertEqual(meta["effective_weight"], meta["weight"])
            self.assertEqual(meta["contribution"], round(meta["weight"] * meta["score"] / 100, 2))
        total = sum(m["contribution"] for m in result["breakdown"].values())
        self.assertEqual(result["score"], round(total))

    def test_weighted_contribution_matches_formula(self):
        data = _full_data()
        data["listing_quality"] = {"score": 100, "available": True, "level": "excellent"}
        # Other components stay at their default scores via the shared data dict.
        result = scoring.compute_property_intelligence(data)
        self.assertEqual(result["breakdown"]["listing_quality"]["contribution"], 25.0)

    def test_unavailable_component_redistributes_weight(self):
        data = _full_data()
        data["price"] = {"available": False}
        result = scoring.compute_property_intelligence(data)
        bd = result["breakdown"]
        self.assertEqual(bd["price_value"]["availability"], "unavailable")
        self.assertIsNone(bd["price_value"]["contribution"])
        # Remaining effective weights must still sum to 100.
        effective = [m["effective_weight"] for m in bd.values() if m["availability"] == "available"]
        self.assertAlmostEqual(sum(effective), 100.0, places=6)
        total = sum(m["contribution"] for m in bd.values() if m["contribution"] is not None)
        self.assertEqual(result["score"], round(total))
        self.assertIn(result["score"], range(0, 101))

    def test_all_unavailable_is_none_not_zero(self):
        data = _full_data()
        for key in ("listing_quality", "price", "location", "photos", "trust", "demand"):
            data[key] = {"available": False}
        result = scoring.compute_property_intelligence(data)
        self.assertIsNone(result["score"])
        self.assertEqual(result["confidence"], "none")

    def test_deterministic_repeatable(self):
        a = scoring.compute_property_intelligence(_full_data())
        b = scoring.compute_property_intelligence(_full_data())
        self.assertEqual(a, b)

    def test_confidence_tiers(self):
        high = scoring.compute_property_intelligence(_full_data())
        self.assertEqual(high["confidence"], "high")
        self.assertIn("strong listing data", high["confidence_reasons"])

        low_data = _full_data()
        low_data["demand"] = {
            "own": {"views": 0, "saves": 0, "requests": 0},
            "area": {"score": 0, "total_signals": 0},
        }
        low_data["price"] = {"available": True, "classification": "fair_price", "sample_size": 1}
        low = scoring.compute_property_intelligence(low_data)
        self.assertIn("limited booking history", low["confidence_reasons"])
        self.assertNotEqual(low["confidence"], "high")

    def test_price_classification_scale(self):
        for classification, expected in (
            ("great_deal", 95),
            ("good_price", 90),
            ("fair_price", 75),
            ("above_average", 45),
            ("overpriced", 20),
        ):
            data = _full_data()
            data["price"] = {
                "available": True,
                "classification": classification,
                "message": "x",
                "sample_size": 8,
            }
            result = scoring.compute_property_intelligence(data)
            self.assertEqual(result["breakdown"]["price_value"]["score"], expected)

    def test_photo_anomaly_deducts_never_verdicts(self):
        clean = scoring.compute_property_intelligence(_full_data())
        risky = _full_data()
        risky["photos"]["anomalies"] = [("duplicate_image", "high"), ("photo_geo_mismatch", "low")]
        score_risky = scoring.compute_property_intelligence(risky)
        self.assertLess(
            score_risky["breakdown"]["photo_trust"]["score"],
            clean["breakdown"]["photo_trust"]["score"],
        )
        blob = str(score_risky)
        self.assertNotIn("fraudulent", blob)
        note = score_risky["breakdown"]["photo_trust"].get("note", "")
        self.assertIn("reduced", note)

    def test_trust_high_fraud_severity_never_publishes_internal_score(self):
        data = _full_data()
        data["trust"] = {
            "verified": False,
            "nid_verified": False,
            "tenant_verified": False,
            "fraud": {"exists": True, "severity": "high"},
        }
        result = scoring.compute_property_intelligence(data)
        self.assertEqual(result["breakdown"]["trust"]["score"], 0)
        blob = str(result)
        self.assertNotIn("risk_score", blob)
        self.assertNotIn("severity", blob)
        self.assertIn("Verification information is incomplete", blob)

    def test_demand_low_sample_is_unavailable(self):
        data = _full_data()
        data["demand"] = {
            "own": {"views": 0, "saves": 0, "requests": 0},
            "area": {"score": 0, "total_signals": 0},
        }
        result = scoring.compute_property_intelligence(data)
        self.assertEqual(result["breakdown"]["demand"]["availability"], "unavailable")
        self.assertIn("Listing has limited recent demand data.", result["suggestions"])

    def test_stale_lowers_confidence(self):
        data = _full_data()
        data["stale_days"] = 200
        result = scoring.compute_property_intelligence(data)
        self.assertIn("stale listing data", result["confidence_reasons"])

    def test_suggestions_deterministic_and_grounded(self):
        data = _full_data()
        data["price"]["classification"] = "overpriced"
        data["photos"] = {
            "count": 2,
            "has_primary": False,
            "anomalies": [],
            "moderation_risk": 0,
            "gps_consistent": False,
        }
        data["trust"] = {
            "verified": False,
            "nid_verified": False,
            "tenant_verified": False,
            "fraud": {"exists": False},
        }
        data["location"] = {"available": False}
        result = scoring.compute_property_intelligence(data)
        joined = " ".join(result["suggestions"])
        self.assertIn("above comparable listings", joined)
        self.assertIn("Set a primary photo", joined)
        self.assertIn("Add more high-quality photos", joined)
        self.assertIn("Verification information is incomplete", joined)
        self.assertIn("Commute data is unavailable", joined)

    def test_version_and_config_signature(self):
        self.assertEqual(SCORE_VERSION, "property_intelligence_v1")
        weights = dict(scoring.DEFAULT_WEIGHTS)
        sig_a = scoring.config_signature(weights)
        alt = dict(weights)
        alt["demand"] = 15
        alt["trust"] = 10
        sig_b = scoring.config_signature(alt)
        self.assertNotEqual(sig_a, sig_b)
        self.assertEqual(sig_a, scoring.config_signature(weights))


# ---------------------------------------------------------------------------
# Engine + cache integration
# ---------------------------------------------------------------------------


@override_settings(PROPERTY_INTELLIGENCE_ENABLED=True, PROPERTY_INTELLIGENCE_CACHE_TTL_SECONDS=900)
class EngineIntegrationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("pi_owner")
        cls.staff = make_user("pi_staff")
        cls.staff.is_staff = True
        cls.staff.save(update_fields=["is_staff"])
        cls.room = make_room(cls.owner, verified=True)
        attach_images(cls.room, 4)
        cls.market = make_market()

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        # A clean fraud report per test so assertions are deterministic.
        FraudReport.objects.filter(room_id=self.room.id).delete()

    def test_engine_returns_public_payload(self):
        from .engine import get_property_intelligence, public_payload

        result = get_property_intelligence(self.room)
        self.assertTrue(public_payload is not None)
        self.assertIn(result["score"], range(0, 101))
        self.assertEqual(
            set(result),
            {
                "room_id",
                "score",
                "confidence",
                "confidence_reasons",
                "score_version",
                "computed_at",
                "breakdown",
                "strengths",
                "suggestions",
                "data_freshness",
                "disclaimer",
            },
        )
        self.assertIn("not a property valuation", result["disclaimer"])

    def test_engine_internal_includes_provenance_and_metadata(self):
        from .engine import get_property_intelligence

        result = get_property_intelligence(self.room, include_internal=True)
        self.assertIn("provenance", result)
        self.assertIn("_engine", result)
        provenance = result["provenance"]
        self.assertEqual(provenance["market"]["sample_size"], 10)
        self.assertEqual(provenance["market"]["avg_price"], 10000.0)
        self.assertEqual(provenance["photos"]["count"], 4)
        self.assertEqual(provenance["market"]["benchmark"], "segment_avg")
        self.assertEqual(result["_engine"]["version"], SCORE_VERSION)
        self.assertTrue(result["_engine"]["config_signature"])

    def test_cache_hit_and_config_invalidation(self):
        from .engine import get_property_intelligence

        first = get_property_intelligence(self.room)
        second = get_property_intelligence(self.room)
        self.assertEqual(first, second)

        with override_settings(
            PROPERTY_INTELLIGENCE_WEIGHTS={
                "listing_quality": 40,
                "price_value": 20,
                "location": 15,
                "photo_trust": 10,
                "trust": 10,
                "demand": 5,
            }
        ):
            changed = get_property_intelligence(self.room, include_internal=True)
            # New config mints a new key — a fresh compute with the new weights.
            self.assertFalse(changed["_engine"]["cache_hit"])
            self.assertEqual(changed["_engine"]["weights"]["listing_quality"], 40)

    def test_price_change_invalidates_cached_score(self):
        from .engine import get_property_intelligence

        before = get_property_intelligence(self.room)
        self.assertEqual(before["breakdown"]["price_value"]["score"], 75)  # fair price
        self.room.price = 16000  # ~60% above segment avg -> overpriced
        self.room.save()  # post_save signal must expire the cached entry
        after = get_property_intelligence(self.room)
        self.assertEqual(after["breakdown"]["price_value"]["score"], 20)
        self.assertIn("above comparable listings", " ".join(after["suggestions"]))

    def test_insufficient_market_marks_price_unavailable(self):
        from .engine import get_property_intelligence

        self.market.sample_size = 1
        self.market.save()
        result = get_property_intelligence(self.room)
        self.assertEqual(result["breakdown"]["price_value"]["availability"], "unavailable")
        self.assertIsNone(result["breakdown"]["price_value"]["contribution"])
        self.assertIn(result["score"], range(0, 101))

    def test_fraud_signal_lowers_trust_but_never_exposed_publicly(self):
        from .engine import get_property_intelligence, invalidate_for_room

        clean = get_property_intelligence(self.room)
        report = FraudReport.objects.create(
            room=self.room,
            score=90,
            severity=FraudReport.Severity.HIGH,
            status=FraudReport.Status.OPEN,
        )
        FraudSignal.objects.create(
            report=report,
            detector=FraudSignal.Detector.DUPLICATE_IMAGE,
            severity=FraudReport.Severity.HIGH,
            message="duplicate photo",
        )
        # Fraud reports arrive out-of-band (scan pipeline); the same-config
        # cache is expired explicitly, mirroring production invalidation.
        invalidate_for_room(self.room.id)
        risky = get_property_intelligence(self.room)
        self.assertLess(risky["breakdown"]["trust"]["score"], clean["breakdown"]["trust"]["score"])
        self.assertNotIn("provenance", risky)
        self.assertNotIn("90", str(risky["breakdown"]))

    def test_insufficient_demand_is_unavailable(self):
        room = make_room(self.owner, area="Savar", title="Savar Quiet Room", lat=23.85, lng=90.27)
        from .engine import get_property_intelligence

        result = get_property_intelligence(room)
        self.assertEqual(result["breakdown"]["demand"]["availability"], "unavailable")
        self.assertIn("limited recent demand data", " ".join(result["suggestions"]))
        self.assertIn(result["score"], range(0, 101))


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


@override_settings(PROPERTY_INTELLIGENCE_ENABLED=True)
class PropertyIntelligenceApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("api_owner")
        cls.staff = make_user("api_staff")
        cls.staff.is_staff = True
        cls.staff.save(update_fields=["is_staff"])
        cls.room = make_room(cls.owner, verified=True)
        attach_images(cls.room, 4)
        make_market()

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        FraudReport.objects.filter(room_id=self.room.id).delete()

    def test_public_endpoint_shape(self):
        res = self.client.get(f"/api/v1/property-intelligence/{self.room.id}/")
        self.assertEqual(res.status_code, 200, res.data)
        data = res.json()
        self.assertIn(data["score"], range(0, 101))
        self.assertIn(data["confidence"], ("high", "medium", "low", "none"))
        self.assertEqual(data["score_version"], SCORE_VERSION)
        for name in (
            "listing_quality",
            "price_value",
            "location",
            "photo_trust",
            "trust",
            "demand",
        ):
            self.assertIn(name, data["breakdown"])
            comp = data["breakdown"][name]
            self.assertIn("weight", comp)
            self.assertIn("contribution", comp)
            self.assertIn("availability", comp)
        self.assertNotIn("provenance", data)
        self.assertNotIn("_engine", data)

    def test_public_endpoint_does_not_leak_fraud_internals(self):
        FraudReport.objects.create(room=self.room, score=95, severity=FraudReport.Severity.HIGH)
        res = self.client.get(f"/api/v1/property-intelligence/{self.room.id}/")
        self.assertEqual(res.status_code, 200)
        blob = json = res.json()
        self.assertNotIn("provenance", blob)
        self.assertNotIn("_engine", blob)
        self.assertNotIn("risk_score", str(json))
        self.assertNotIn("detector_names", str(json))
        # Public text never fabricates a verdict.
        self.assertNotIn("fraudulent", str(json))

    def test_invalid_room_404(self):
        res = self.client.get("/api/v1/property-intelligence/99999999/")
        self.assertEqual(res.status_code, 404)
        self.assertIn("detail", res.json())

    def test_staff_endpoint_requires_admin(self):
        from rest_framework.test import APIClient as Client

        anon = Client()
        res = anon.get(f"/api/v1/property-intelligence/{self.room.id}/staff/")
        self.assertEqual(res.status_code, 401)

        user_client = Client()
        user_client.force_authenticate(user=self.owner)
        res = user_client.get(f"/api/v1/property-intelligence/{self.room.id}/staff/")
        self.assertEqual(res.status_code, 403)

        staff_client = Client()
        staff_client.force_authenticate(user=self.staff)
        res = staff_client.get(f"/api/v1/property-intelligence/{self.room.id}/staff/")
        self.assertEqual(res.status_code, 200, res.data)
        json_data = res.json()
        self.assertIn("provenance", json_data)
        self.assertIn("_engine", json_data)
        self.assertEqual(json_data["provenance"]["market"]["sample_size"], 10)

    def test_serializer_badge_backward_compatible(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(f"/api/v1/rooms/{self.room.id}/")
        self.assertEqual(res.status_code, 200, res.data)
        quality = res.data["listing_quality"]  # unchanged chip
        self.assertIn("score", quality)
        self.assertIn("suggestions", quality)
        badge = res.data["property_intelligence_score"]
        self.assertIn(badge["score"], range(0, 101))
        self.assertEqual(badge["score_version"], SCORE_VERSION)

    def test_serializer_badge_disabled_is_null(self):
        self.client.force_authenticate(user=self.owner)
        with override_settings(PROPERTY_INTELLIGENCE_SERIALIZER_ENABLED=False):
            res = self.client.get(f"/api/v1/rooms/{self.room.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data["property_intelligence_score"])


# ---------------------------------------------------------------------------
# Agent tool
# ---------------------------------------------------------------------------

MOCK_SETTINGS = override_settings(
    AI_TELEMETRY_ENABLED=True,
    AGENTS_DEBUG_TOOLS=True,
    AI_AGENT_LLM_PROVIDER="mock_llm",
)


@MOCK_SETTINGS
class PropertyIntelligenceToolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("tool_owner")
        cls.room = make_room(cls.owner, verified=True)
        attach_images(cls.room, 4)
        make_market()

    def setUp(self):
        from agents.tools import AgentToolRegistry, register_builtin_tools

        AgentToolRegistry.clear()
        register_builtin_tools()

    def tearDown(self):
        from agents.tools import AgentToolRegistry

        AgentToolRegistry.clear()

    def _tool(self):
        from agents.tools import AgentToolRegistry

        return AgentToolRegistry.get("property.intelligence")

    def test_registered_read_only_with_schema(self):
        from agents.tools import READ_ONLY

        tool = self._tool()
        self.assertIsNotNone(tool)
        self.assertEqual(tool.capability, READ_ONLY)
        self.assertTrue(tool.enabled)
        self.assertIn("room_id", tool.input_schema.get("properties", {}))
        self.assertEqual(tool.input_schema["required"], ["room_id"])

    def test_schema_validation(self):
        from agents.tools import ToolValidationError

        tool = self._tool()
        tool.validate_arguments({"room_id": self.room.id})
        with self.assertRaises(ToolValidationError):
            tool.validate_arguments({})
        with self.assertRaises(ToolValidationError):
            tool.validate_arguments({"room_id": "not-an-int"})
        with self.assertRaises(ToolValidationError):
            tool.validate_arguments({"room_id": self.room.id, "surprise": True})

    def test_executor_grounded_and_read_only(self):
        from agents.tools import RESULT_OK

        from .engine import get_property_intelligence, public_payload

        tool = self._tool()
        full = get_property_intelligence(self.room)
        expected_light = {
            "room_id": full["room_id"],
            "score": full["score"],
            "confidence": full["confidence"],
            "score_version": full["score_version"],
            "computed_at": full["computed_at"],
            "strengths": full["strengths"],
            "suggestions": full["suggestions"],
            "disclaimer": full["disclaimer"],
        }
        outcome = tool.execute({"room_id": self.room.id}, {"actor": None})
        self.assertTrue(outcome[RESULT_OK])
        # Light surface by default: grounded exactly to the engine, nothing invented.
        self.assertEqual(outcome["data"], expected_light)
        self.assertNotIn("provenance", outcome["data"])
        self.assertNotIn("breakdown", outcome["data"])

        full_outcome = tool.execute(
            {"room_id": self.room.id, "include_breakdown": True}, {"actor": None}
        )
        self.assertTrue(full_outcome[RESULT_OK])
        self.assertEqual(full_outcome["data"], public_payload(full))
        self.assertIn("breakdown", full_outcome["data"])

    def test_executor_unknown_room(self):
        tool = self._tool()
        outcome = tool.execute({"room_id": 99999999}, {"actor": None})
        self.assertFalse(outcome["ok"])
        self.assertIn("not found", outcome["error"])

    def test_run_through_session_is_audited_and_telemetry_enriched(self):
        from agents.models import AgentToolCall
        from agents.services import create_conversation, create_run, register_agent
        from agents.session import AgentSession
        from ai_intelligence.services import register_feature

        actor = make_user("pi_staff_actor")
        actor.is_staff = True
        actor.save(update_fields=["is_staff"])
        register_feature("rentora.agent", "AI Agents", is_enabled=True)
        agent = register_agent(
            key="pi.tool",
            name="Pi Tool",
            status="active",
            audience="staff",
            permission="operator",
            feature_id="rentora.agent",
            prompt_key="",
            provider="mock_llm",
            system_instructions="Use the property.intelligence tool to report the listing score.",
            enabled_tools=["property.intelligence"],
        )
        conv = create_conversation(agent, actor, title="t")
        run, _ = create_run(conv, "score my listing", actor=actor)
        run.metadata["mock_plan"] = [
            {
                "type": "tool_call",
                "name": "property.intelligence",
                "arguments": {"room_id": self.room.id},
            },
            {"type": "text", "content": "Here is the score."},
        ]
        run.save()
        AgentSession(conv, actor=actor).execute(run)
        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        call = AgentToolCall.objects.get(run=run, tool_name="property.intelligence")
        self.assertEqual(call.permission_decision, "read_allowed")
        self.assertEqual(call.execution_status, "executed")
        self.assertTrue(call.result.get("ok"))
        self.assertGreater(call.duration_ms, 0)


class AdminInspectorTests(APITestCase):
    """Phase 19.1 staff UI — read-only Django admin inspector for a room."""

    client_class = Client  # plain Django client so session login works

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("insp_owner")
        cls.admin = User.objects.create_user(
            username="insp_admin",
            email="admin@example.com",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        cls.room = make_room(cls.owner, verified=True)
        attach_images(cls.room, 4)
        make_market()

    def test_inspector_renders_score_and_breakdown(self):
        from django.urls import reverse

        url = reverse("admin:rooms_room_property_intelligence", args=[self.room.pk])
        self.assertTrue(self.client.login(username="insp_admin", password="x"))
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Property Intelligence")
        self.assertContains(res, "listing_quality")
        self.assertContains(res, "price_value")

    def test_inspector_redirects_for_non_staff(self):
        from django.urls import reverse

        url = reverse("admin:rooms_room_property_intelligence", args=[self.room.pk])
        self.client.login(username="insp_owner", password="x")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)  # staff_member_required

    def test_inspector_404_for_unknown_room(self):
        from django.urls import reverse

        url = reverse("admin:rooms_room_property_intelligence", args=[99999999])
        self.client.login(username="insp_admin", password="x")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)


# ---------------------------------------------------------------------------
# Regression: listing quality stays byte-compatible
# ---------------------------------------------------------------------------


class ListingQualityCompatibilityTests(APITestCase):
    def test_existing_quality_surface_unchanged(self):
        owner = make_user("reg_owner")
        room = make_room(owner)
        attach_images(room, 4)
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertEqual(
            set(result),
            {"score", "level", "category_scores", "suggestions"},
        )
        self.assertIn(result["level"], ("excellent", "good", "fair", "needs_improvement", "poor"))
        self.assertTrue(0.0 <= result["score"] <= 100.0)

    def test_detail_returns_both_fields_without_regression(self):
        owner = make_user("reg_owner2")
        room = make_room(owner)
        attach_images(room, 4)
        make_market()
        self.client.force_authenticate(user=owner)
        res = self.client.get(f"/api/v1/rooms/{room.id}/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("listing_quality", res.data)
        self.assertIn("property_intelligence_score", res.data)
