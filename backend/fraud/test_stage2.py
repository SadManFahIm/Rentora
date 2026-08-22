"""Stage 2 — Shared Trust/Fraud Infrastructure tests.

Covers every new/modified component from Phase 17 Stage 2:
- Extended FraudSignal detector choices
- Extended Review moderation_status + trust_score
- Extended TenantVerification liveness/face_match fields
- EXIF GPS extraction utilities
- Provider base abstraction (BaseProvider, ProviderResult, Registry)
- Trust utilities (is_admin_user, log_trust_action, compute_haversine_distance)
- Phase 17 feature flag seeds
- Phase 17 Celery task stubs
- ml_models app (ModelVersion, DriftMetric, RetrainRequest)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditLogEntry
from fraud.models import FraudReport, FraudSignal
from fraud.services.provider_base import (
    BaseProvider,
    FailureType,
    ProviderFailure,
    ProviderResult,
    Registry,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username="testuser", role="tenant", **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        role=role,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# FraudSignal extended detector choices
# ---------------------------------------------------------------------------


class FraudSignalDetectorChoicesTests(TestCase):
    def test_phase17_detectors_exist(self):
        expected = [
            "photo_geo_mismatch",
            "liveness_failed",
            "face_match_failed",
            "review_fake",
            "review_spam",
            "kyc_liveness_missing",
        ]
        for detector_key in expected:
            self.assertIn(
                detector_key,
                [c[0] for c in FraudSignal.Detector.choices],
                f"Detector {detector_key} not found in FraudSignal.Detector.choices",
            )

    def test_existing_detectors_still_present(self):
        existing = [
            "duplicate_listing",
            "suspicious_price",
            "missing_images",
            "rapid_listing",
            "unverified_owner",
            "description_similarity",
            "duplicate_image",
            "manipulated_image",
            "fraud_ring",
        ]
        for detector_key in existing:
            self.assertIn(
                detector_key,
                [c[0] for c in FraudSignal.Detector.choices],
            )

    def test_can_create_signal_with_phase17_detector(self):
        from rooms.models import Room

        owner = _make_user("owner_sig")
        room = Room.objects.create(
            owner=owner,
            title="Test Room",
            description="Test",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="12 Mirpur Rd",
            lat=23.8,
            lng=90.3,
            amenities=[],
            size_sqft=200,
        )
        report, _ = FraudReport.objects.get_or_create(
            room=room, defaults={"score": 50, "severity": "medium"}
        )
        report.score = 50
        report.severity = "medium"
        report.save()
        signal = FraudSignal.objects.create(
            report=report,
            detector=FraudSignal.Detector.PHOTO_GEO_MISMATCH,
            severity="medium",
            message="GPS mismatch detected.",
            detail={"photo_lat": 23.81, "room_lat": 23.80},
        )
        self.assertEqual(signal.detector, "photo_geo_mismatch")
        self.assertEqual(signal.detail["photo_lat"], 23.81)


# ---------------------------------------------------------------------------
# Review extended fields
# ---------------------------------------------------------------------------


class ReviewModerationTests(TestCase):
    def _make_review(self, **kwargs):
        from bookings.models import Review
        from rooms.models import Room

        owner = _make_user("rev_owner")
        reviewer = _make_user("rev_user")
        room = Room.objects.create(
            owner=owner,
            title="Review Room",
            description="Test",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="12 Mirpur Rd",
            lat=23.8,
            lng=90.3,
            amenities=[],
            size_sqft=200,
        )
        defaults = {
            "room": room,
            "user": reviewer,
            "rating": 4,
            "comment": "Great room!",
        }
        defaults.update(kwargs)
        return Review.objects.create(**defaults)

    def test_default_moderation_status_is_approved(self):
        review = self._make_review()
        self.assertEqual(review.moderation_status, "approved")

    def test_trust_score_default_is_none(self):
        review = self._make_review()
        self.assertIsNone(review.trust_score)

    def test_can_set_moderation_status_pending(self):
        review = self._make_review()
        review.moderation_status = "pending"
        review.save()
        review.refresh_from_db()
        self.assertEqual(review.moderation_status, "pending")

    def test_can_set_trust_score(self):
        review = self._make_review()
        review.trust_score = 85
        review.save()
        review.refresh_from_db()
        self.assertEqual(review.trust_score, 85)

    def test_moderation_status_choices(self):
        from bookings.models import Review

        expected = ["approved", "pending", "rejected", "escalated"]
        actual = [c[0] for c in Review.ModerationStatus.choices]
        for status in expected:
            self.assertIn(status, actual)


# ---------------------------------------------------------------------------
# TenantVerification extended fields
# ---------------------------------------------------------------------------


class TenantVerificationExtendedTests(TestCase):
    def test_liveness_fields_default_empty(self):
        from users.models import TenantVerification

        user = _make_user("kyc_user")
        tv = TenantVerification.objects.create(user=user)
        self.assertEqual(tv.liveness_status, "")
        self.assertIsNone(tv.liveness_score)
        self.assertEqual(tv.face_match_status, "")
        self.assertIsNone(tv.face_match_score)

    def test_can_set_liveness_fields(self):
        from users.models import TenantVerification

        user = _make_user("kyc_user2")
        tv = TenantVerification.objects.create(
            user=user,
            liveness_status="passed",
            liveness_score=92,
            face_match_status="passed",
            face_match_score=88,
        )
        tv.refresh_from_db()
        self.assertEqual(tv.liveness_status, "passed")
        self.assertEqual(tv.liveness_score, 92)
        self.assertEqual(tv.face_match_status, "passed")
        self.assertEqual(tv.face_match_score, 88)


# ---------------------------------------------------------------------------
# EXIF / GPS utilities
# ---------------------------------------------------------------------------


class ExifGpsUtilsTests(TestCase):
    def test_extract_gps_returns_none_for_no_exif(self):
        import io

        from PIL import Image

        from config.exif_utils import extract_gps_from_exif

        # Minimal PNG with no EXIF data
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
        result = extract_gps_from_exif(buf.getvalue())
        self.assertIsNone(result)

    def test_has_gps_data_false_for_png(self):
        import io

        from PIL import Image

        from config.exif_utils import has_gps_data

        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(buf, format="PNG")
        self.assertFalse(has_gps_data(buf.getvalue()))

    def test_extract_gps_returns_none_for_bytes_error(self):
        from config.exif_utils import extract_gps_from_exif

        result = extract_gps_from_exif(b"not an image at all")
        self.assertIsNone(result)

    def test_has_gps_data_returns_false_for_garbage(self):
        from config.exif_utils import has_gps_data

        self.assertFalse(has_gps_data(b"garbage data"))


# ---------------------------------------------------------------------------
# Provider base abstraction
# ---------------------------------------------------------------------------


class ProviderResultTests(TestCase):
    def test_ok_result(self):
        result = ProviderResult.ok("test_provider", data={"key": "val"}, confidence=0.9)
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "test_provider")
        self.assertAlmostEqual(result.confidence, 0.9)
        self.assertEqual(result.data["key"], "val")
        self.assertFalse(result.is_user_failure)
        self.assertFalse(result.is_provider_failure)
        self.assertFalse(result.is_system_failure)

    def test_fail_result_user_failure(self):
        result = ProviderResult.fail(
            "test_provider", "Blurry photo", failure_type=FailureType.USER_FAILURE
        )
        self.assertFalse(result.success)
        self.assertTrue(result.is_user_failure)
        self.assertFalse(result.is_provider_failure)

    def test_fail_result_provider_failure(self):
        result = ProviderResult.fail(
            "test_provider", "Gateway timeout", failure_type=FailureType.PROVIDER_FAILURE
        )
        self.assertTrue(result.is_provider_failure)

    def test_fail_result_system_failure(self):
        result = ProviderResult.fail(
            "test_provider", "DB error", failure_type=FailureType.SYSTEM_FAILURE
        )
        self.assertTrue(result.is_system_failure)


class ProviderFailureTests(TestCase):
    def test_carries_failure_type(self):
        exc = ProviderFailure("down", failure_type=FailureType.PROVIDER_FAILURE)
        self.assertEqual(exc.failure_type, FailureType.PROVIDER_FAILURE)
        self.assertIn("down", str(exc))


class ConcreteProvider(BaseProvider):
    """Minimal concrete provider for testing."""

    name = "test_concrete"

    def _run(self, **kwargs):
        if kwargs.get("fail_user"):
            raise ProviderFailure("bad input", FailureType.USER_FAILURE)
        if kwargs.get("fail_provider"):
            raise ProviderFailure("gateway down", FailureType.PROVIDER_FAILURE)
        if kwargs.get("fail_unexpected"):
            raise ValueError("unexpected")
        return ProviderResult.ok(self.name, data={"result": "ok"})


class BaseProviderTests(TestCase):
    def test_run_returns_result_on_success(self):
        provider = ConcreteProvider()
        result = provider.run()
        self.assertTrue(result.success)
        self.assertEqual(result.data["result"], "ok")

    def test_run_catches_user_failure(self):
        provider = ConcreteProvider()
        result = provider.run(fail_user=True)
        self.assertFalse(result.success)
        self.assertTrue(result.is_user_failure)

    def test_run_catches_provider_failure(self):
        provider = ConcreteProvider()
        result = provider.run(fail_provider=True)
        self.assertFalse(result.success)
        self.assertTrue(result.is_provider_failure)

    def test_run_catches_unexpected_as_system_failure(self):
        provider = ConcreteProvider()
        result = provider.run(fail_unexpected=True)
        self.assertFalse(result.success)
        self.assertTrue(result.is_system_failure)


class RegistryTests(TestCase):
    def setUp(self):
        Registry._providers.clear()

    def tearDown(self):
        Registry._providers.clear()

    @override_settings(TEST_FEATURE_PROVIDER="rules")
    def test_register_and_resolve(self):
        Registry.register("test_feature", "rules", ConcreteProvider)
        resolved = Registry.resolve("test_feature", "TEST_FEATURE_PROVIDER")
        self.assertEqual(resolved, ConcreteProvider)

    @override_settings(NONEXISTENT_SETTING="")
    def test_resolve_returns_none_for_empty_setting(self):
        Registry.register("test_feature", "rules", ConcreteProvider)
        resolved = Registry.resolve("test_feature", "NONEXISTENT_SETTING")
        self.assertIsNone(resolved)

    def test_available_lists_providers(self):
        Registry.register("f", "a", ConcreteProvider)
        Registry.register("f", "b", ConcreteProvider)
        self.assertEqual(sorted(Registry.available("f")), ["a", "b"])


# ---------------------------------------------------------------------------
# Trust utilities
# ---------------------------------------------------------------------------


class IsAdminUserTests(TestCase):
    def test_staff_user_is_admin(self):
        from config.trust_utils import is_admin_user

        user = _make_user("staff", is_staff=True)
        self.assertTrue(is_admin_user(user))

    def test_role_admin_is_admin(self):
        from config.trust_utils import is_admin_user

        user = _make_user("admin_role", role="admin")
        self.assertTrue(is_admin_user(user))

    def test_tenant_is_not_admin(self):
        from config.trust_utils import is_admin_user

        user = _make_user("tenant", role="tenant")
        self.assertFalse(is_admin_user(user))

    def test_none_is_not_admin(self):
        from config.trust_utils import is_admin_user

        self.assertFalse(is_admin_user(None))

    def test_anonymous_is_not_admin(self):
        from config.trust_utils import is_admin_user

        anon = MagicMock(is_authenticated=False)
        self.assertFalse(is_admin_user(anon))


class LogTrustActionTests(TestCase):
    def test_creates_audit_entry_with_prefix(self):
        from config.trust_utils import log_trust_action

        user = _make_user("audit_user")
        entry = log_trust_action(
            actor=user,
            action="review.flag",
            detail={"review_id": 1},
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, "trust.review.flag")
        self.assertEqual(entry.actor, user)

    def test_audit_entry_stored_in_db(self):
        from config.trust_utils import log_trust_action

        before_count = AuditLogEntry.objects.count()
        log_trust_action(action="system.test")
        self.assertEqual(AuditLogEntry.objects.count(), before_count + 1)


class HaversineTests(TestCase):
    def test_same_point_returns_zero(self):
        from config.trust_utils import compute_haversine_distance

        d = compute_haversine_distance(23.81, 90.41, 23.81, 90.41)
        self.assertAlmostEqual(d, 0.0, places=1)

    def test_known_distance_dhaka(self):
        from config.trust_utils import compute_haversine_distance

        # Dhanmondi to Gulshan: roughly 7-8 km
        dhanmondi = (23.7509, 90.3743)
        gulshan = (23.7925, 90.4078)
        d = compute_haversine_distance(*dhanmondi, *gulshan)
        self.assertGreater(d, 3000)  # > 3 km
        self.assertLess(d, 12000)  # < 12 km


# ---------------------------------------------------------------------------
# Feature flag seeds
# ---------------------------------------------------------------------------


class Phase17FlagSeedsTests(TestCase):
    def test_sync_flags_includes_phase17(self):
        from feature_flags.management.commands.sync_flags import DEFAULT_FLAGS

        phase17_keys = [f["key"] for f in DEFAULT_FLAGS if f["key"].startswith("phase17.")]
        expected = [
            "phase17.scam_graph",
            "phase17.kyc_liveness",
            "phase17.kyc_face_match",
            "phase17.photo_geo",
            "phase17.review_moderation",
            "phase17.review_trust",
            "phase17.model_monitoring",
        ]
        for key in expected:
            self.assertIn(key, phase17_keys)

    def test_sync_flags_creates_phase17_flags(self):
        from django.core.management import call_command

        from feature_flags.models import FeatureFlag, invalidate_cache

        call_command("sync_flags", verbosity=0)
        invalidate_cache()
        for key in [
            "phase17.scam_graph",
            "phase17.kyc_liveness",
            "phase17.review_trust",
        ]:
            flag = FeatureFlag.objects.get(key=key)
            self.assertEqual(flag.status, "disabled")
            self.assertEqual(flag.rollout_percentage, 0)


# ---------------------------------------------------------------------------
# Celery task stubs
# ---------------------------------------------------------------------------


class Phase17TaskStubTests(TestCase):
    def test_rebuild_fraud_graph(self):
        from fraud.tasks import rebuild_fraud_graph

        result = rebuild_fraud_graph()
        self.assertIsInstance(result, dict)
        self.assertIn("nodes", result)

    def test_update_graph_incremental(self):
        from fraud.tasks import update_graph_incremental

        result = update_graph_incremental()
        self.assertIsInstance(result, dict)
        self.assertIn("new_nodes", result)

    def test_scan_review_trust(self):
        from fraud.tasks import scan_review_trust

        result = scan_review_trust()
        self.assertIsInstance(result, dict)
        self.assertIn("scored", result)
        self.assertIn("flagged", result)

    def test_detect_review_anomalies(self):
        from fraud.tasks import detect_review_anomalies

        result = detect_review_anomalies()
        self.assertIsInstance(result, dict)
        self.assertIn("anomalies", result)

    def test_check_model_drift_is_implemented(self):
        from fraud.tasks import check_model_drift

        result = check_model_drift()
        self.assertIsInstance(result, dict)
        self.assertIn("metrics_computed", result)
        self.assertNotEqual(result.get("status"), "stub")

    def test_purge_expired_liveness(self):
        from fraud.tasks import purge_expired_liveness

        result = purge_expired_liveness()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "ok")
        self.assertIn("deleted", result)

    def test_alert_graph_anomalies(self):
        from fraud.tasks import alert_graph_anomalies

        result = alert_graph_anomalies()
        self.assertIsInstance(result, dict)
        self.assertIn("alerted", result)


# ---------------------------------------------------------------------------
# Beat schedule wiring
# ---------------------------------------------------------------------------


class BeatScheduleWiringTests(TestCase):
    def test_phase17_tasks_in_beat_schedule(self):
        from django.conf import settings

        schedule = settings.CELERY_BEAT_SCHEDULE
        expected_tasks = [
            "fraud.tasks.rebuild_fraud_graph",
            "fraud.tasks.update_graph_incremental",
            "fraud.tasks.scan_review_trust",
            "fraud.tasks.detect_review_anomalies",
            "fraud.tasks.check_model_drift",
            "fraud.tasks.purge_expired_liveness",
            "fraud.tasks.alert_graph_anomalies",
        ]
        schedule_tasks = [entry["task"] for entry in schedule.values()]
        for task in expected_tasks:
            self.assertIn(task, schedule_tasks, f"Task {task} not in CELERY_BEAT_SCHEDULE")


# ---------------------------------------------------------------------------
# ML Models API (smoke test)
# ---------------------------------------------------------------------------


class MlModelsApiTests(TestCase):
    def setUp(self):
        self.admin = _make_user("ml_admin", is_staff=True, role="admin")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_model_version_list_empty(self):
        resp = self.client.get("/api/v1/ml/models/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_model_version_list_non_admin_forbidden(self):
        tenant = _make_user("ml_tenant")
        self.client.force_authenticate(user=tenant)
        resp = self.client.get("/api/v1/ml/models/")
        self.assertEqual(resp.status_code, 403)

    def test_drift_metric_list_empty(self):
        resp = self.client.get("/api/v1/ml/drift/")
        self.assertEqual(resp.status_code, 200)

    def test_retrain_request_list_empty(self):
        resp = self.client.get("/api/v1/ml/retrain/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# INSTALLED_APPS check
# ---------------------------------------------------------------------------


class InstalledAppsTests(TestCase):
    def test_ml_models_in_installed_apps(self):
        from django.conf import settings

        self.assertIn("ml_models", settings.INSTALLED_APPS)
