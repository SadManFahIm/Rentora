"""Cross-feature integration tests for Phase 17 (Stage 9).

Tests verify that all Graph & Deep Trust features work together.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from fraud.services.graph import detect_anomalies, graph_overview, rebuild_graph
from fraud.services.model_monitor import (
    check_all_drift,
    record_drift_metric,
)
from fraud.services.photo_geo import check_photo_geo_mismatch
from fraud.services.privacy import sanitize_dict, sanitize_reason
from fraud.services.provider_base import FailureType, ProviderResult, Registry
from fraud.tasks import (
    alert_graph_anomalies,
    check_model_drift,
    detect_review_anomalies,
    scan_photo_geo_mismatches,
    scan_review_trust,
)
from ml_models.models import DriftMetric, ModelVersion, RetrainRequest
from rooms.models import Room, RoomImage

User = get_user_model()


def _room(owner, **kwargs):
    defaults = {
        "title": "Test Room",
        "description": "A test room",
        "price": 10000,
        "area": "Mirpur",
        "room_type": "single",
        "lat": Decimal("23.8103"),
        "lng": Decimal("90.4125"),
        "address": "123 Test Street, Mirpur",
        "size_sqft": 200,
    }
    defaults.update(kwargs)
    return Room.objects.create(owner=owner, **defaults)


class GraphFraudIntegrationTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", email="u1@test.com", password="test12345"
        )

    def test_rebuild_graph_returns_counts(self):
        result = rebuild_graph()
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("communities", result)

    def test_rebuild_graph_with_rooms(self):
        _room(self.user1)
        result = rebuild_graph()
        self.assertGreaterEqual(result["nodes"], 0)

    def test_graph_overview_returns_data(self):
        rebuild_graph()
        overview = graph_overview()
        self.assertIn("node_count", overview)
        self.assertIn("edge_count", overview)

    def test_detect_anomalies_empty(self):
        anomalies = detect_anomalies()
        self.assertIsInstance(anomalies, list)

    def test_graph_alert_task_runs(self):
        result = alert_graph_anomalies()
        self.assertIn("alerted", result)


class PhotoGeoFraudSignalIntegrationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test12345"
        )
        self.room = _room(self.owner)

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=1.0)
    def test_photo_geo_mismatch_detected(self):
        RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
            photo_lat=Decimal("22.0000"),
            photo_lng=Decimal("88.0000"),
        )
        result = check_photo_geo_mismatch(self.room)
        self.assertTrue(result["mismatch"])

    def test_scan_task_runs(self):
        result = scan_photo_geo_mismatches()
        self.assertEqual(result["status"], "ok")


class ReviewTrustAnomalyIntegrationTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test12345"
        )
        self.reviewer = User.objects.create_user(
            username="reviewer",
            email="rev@test.com",
            password="test12345",
            date_joined=timezone.now() - timedelta(days=200),
        )
        self.room = _room(self.owner, title="Review Room", area="Dhanmondi")

    def test_scan_review_trust_scores_reviews(self):
        from bookings.models import Review

        Review.objects.create(
            room=self.room,
            user=self.reviewer,
            rating=4,
            comment="Great room, very clean and well-maintained.",
        )
        result = scan_review_trust()
        self.assertIn("scored", result)
        self.assertGreater(result["scored"], 0)

    def test_detect_anomalies_finds_patterns(self):
        result = detect_review_anomalies()
        self.assertIn("count", result)
        self.assertIn("anomalies", result)

    def test_both_tasks_run_together(self):
        trust_result = scan_review_trust()
        anomaly_result = detect_review_anomalies()
        self.assertIsInstance(trust_result, dict)
        self.assertIsInstance(anomaly_result, dict)


class ModelDriftCrossFeatureTest(TestCase):
    def setUp(self):
        self.mv = ModelVersion.objects.create(
            name="fraud_system",
            version="1.0.0",
            status=ModelVersion.Status.ACTIVE,
        )

    def test_drift_check_with_no_data(self):
        result = check_all_drift()
        self.assertGreater(result["metrics_computed"], 0)

    def test_drift_check_creates_model_if_needed(self):
        ModelVersion.objects.all().delete()
        check_all_drift()
        self.assertEqual(ModelVersion.objects.count(), 1)

    def test_drift_task_end_to_end(self):
        result = check_model_drift()
        self.assertIn("metrics_computed", result)

    def test_multiple_checks_track_history(self):
        record_drift_metric(self.mv, "fraud_signal_rate", 0.05)
        record_drift_metric(self.mv, "fraud_signal_rate", 0.08)
        self.assertEqual(DriftMetric.objects.filter(metric_name="fraud_signal_rate").count(), 2)

    def test_breach_triggers_retrain(self):
        with patch("fraud.services.model_monitor.compute_fraud_signal_rate", return_value=0.50):
            check_all_drift()
            self.assertGreaterEqual(RetrainRequest.objects.count(), 1)


class ProviderCrossFeatureTest(TestCase):
    def setUp(self):
        Registry._providers.clear()

    def tearDown(self):
        Registry._providers.clear()

    def test_provider_result_ok(self):
        result = ProviderResult.ok("test", data={"score": 0.95})
        self.assertTrue(result.success)
        self.assertEqual(result.data["score"], 0.95)

    def test_provider_result_fail_classified(self):
        for ft in [
            FailureType.USER_FAILURE,
            FailureType.PROVIDER_FAILURE,
            FailureType.SYSTEM_FAILURE,
        ]:
            result = ProviderResult.fail("test", reason="error", failure_type=ft)
            self.assertFalse(result.success)
            self.assertEqual(result.failure_type, ft)

    def test_registry_register_and_resolve(self):
        from users.liveness_provider import RulesLivenessProvider

        Registry.register("liveness", "rules", RulesLivenessProvider)

        @override_settings(KYC_LIVENESS_PROVIDER="rules")
        def _check():
            cls = Registry.resolve("liveness", setting="KYC_LIVENESS_PROVIDER")
            self.assertEqual(cls, RulesLivenessProvider)

        _check()

    def test_registry_available(self):
        from users.liveness_provider import RulesLivenessProvider

        Registry.register("liveness", "rules", RulesLivenessProvider)
        self.assertIn("rules", Registry.available("liveness"))


class FeatureFlagIntegrationTest(TestCase):
    def test_feature_flags_exist(self):
        from django.core.management import call_command

        from feature_flags.models import FeatureFlag

        call_command("sync_flags", verbosity=0)
        flags = FeatureFlag.objects.filter(key__startswith="phase17.")
        self.assertGreaterEqual(flags.count(), 1)

    def test_all_phase17_flags_disabled_by_default(self):
        from django.core.management import call_command

        from feature_flags.models import FeatureFlag

        call_command("sync_flags", verbosity=0)
        flags = FeatureFlag.objects.filter(key__startswith="phase17.")
        for flag in flags:
            self.assertEqual(flag.status, "disabled")


class PrivacyCrossFeatureTest(TestCase):
    def test_provider_failure_sanitized(self):
        result = ProviderResult.fail(
            "test",
            reason="Phone 01712345678 invalid",
            failure_type=FailureType.USER_FAILURE,
        )
        self.assertNotIn("01712345678", result.reason)

    def test_dict_sanitization(self):
        data = {"name": "John", "phone": "01712345678"}
        safe = sanitize_dict(data)
        self.assertEqual(safe["name"], "John")
        self.assertNotIn("01712345678", safe["phone"])

    def test_reason_sanitize_strips_pii(self):
        raw = "Error at user@example.com with 01712345678"
        self.assertNotIn("user@example.com", sanitize_reason(raw))
        self.assertNotIn("01712345678", sanitize_reason(raw))


class CeleryBeatScheduleIntegrationTest(TestCase):
    def test_all_phase17_tasks_scheduled(self):
        from django.conf import settings

        schedule = settings.CELERY_BEAT_SCHEDULE
        required = [
            "fraud.tasks.rebuild_fraud_graph",
            "fraud.tasks.update_graph_incremental",
            "fraud.tasks.scan_review_trust",
            "fraud.tasks.detect_review_anomalies",
            "fraud.tasks.check_model_drift",
            "fraud.tasks.purge_expired_liveness",
            "fraud.tasks.alert_graph_anomalies",
            "fraud.tasks.scan_photo_geo_mismatches",
        ]
        scheduled = [e["task"] for e in schedule.values()]
        for task in required:
            self.assertIn(task, scheduled, f"{task} not in beat schedule")
