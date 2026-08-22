"""Tests for model drift monitoring (Phase 17, Stage 7)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fraud.services.model_monitor import (
    DRIFT_THRESHOLDS,
    check_all_drift,
    compute_fraud_signal_rate,
    compute_photo_geo_mismatch_rate,
    compute_review_trust_avg,
    get_thresholds,
    record_drift_metric,
)
from ml_models.models import DriftMetric, ModelVersion, RetrainRequest

User = get_user_model()

ACTIVE_MODEL_DATA = {
    "name": "fraud_system",
    "version": "1.0.0",
    "description": "Test model",
    "status": ModelVersion.Status.ACTIVE,
}


class ThresholdConfigTests(TestCase):
    def test_get_thresholds_returns_defaults(self):
        t = get_thresholds()
        self.assertIn("fraud_signal_rate", t)
        self.assertIn("review_trust_avg", t)
        self.assertIn("photo_geo_mismatch_rate", t)

    @override_settings(MODEL_DRIFT_THRESHOLDS={"custom_metric": {"max": 0.5}})
    def test_get_thresholds_from_settings(self):
        t = get_thresholds()
        self.assertIn("custom_metric", t)

    def test_default_thresholds_have_baseline(self):
        for name, t in DRIFT_THRESHOLDS.items():
            self.assertIn("baseline", t, f"{name} missing baseline")


class ComputeMetricsTests(TestCase):
    def test_fraud_signal_rate_no_data(self):
        rate = compute_fraud_signal_rate()
        self.assertEqual(rate, 0.0)

    def test_review_trust_avg_no_data(self):
        avg = compute_review_trust_avg()
        self.assertEqual(avg, 0.0)

    def test_photo_geo_mismatch_rate_no_data(self):
        rate = compute_photo_geo_mismatch_rate()
        self.assertEqual(rate, 0.0)


class RecordDriftMetricTests(TestCase):
    def setUp(self):
        self.mv = ModelVersion.objects.create(**ACTIVE_MODEL_DATA)

    def test_record_within_bounds(self):
        result = record_drift_metric(self.mv, "fraud_signal_rate", 0.10)
        self.assertFalse(result["breached"])
        self.assertEqual(DriftMetric.objects.count(), 1)
        metric = DriftMetric.objects.first()
        self.assertFalse(metric.threshold_breached)

    def test_record_breach_above_max(self):
        result = record_drift_metric(self.mv, "fraud_signal_rate", 0.35)
        self.assertTrue(result["breached"])
        metric = DriftMetric.objects.first()
        self.assertTrue(metric.threshold_breached)
        self.assertEqual(metric.threshold_max, 0.30)

    def test_record_breach_below_min(self):
        result = record_drift_metric(self.mv, "review_trust_avg", 40.0)
        self.assertTrue(result["breached"])

    def test_no_min_threshold(self):
        result = record_drift_metric(self.mv, "fraud_signal_rate", 0.01)
        self.assertFalse(result["breached"])

    def test_retrain_request_created_on_breach(self):
        record_drift_metric(self.mv, "fraud_signal_rate", 0.35)
        self.assertEqual(RetrainRequest.objects.count(), 1)
        rr = RetrainRequest.objects.first()
        self.assertEqual(rr.status, RetrainRequest.Status.PENDING)
        self.assertIn("fraud_signal_rate", rr.reason)

    def test_no_duplicate_retrain_requests(self):
        record_drift_metric(self.mv, "fraud_signal_rate", 0.35)
        record_drift_metric(self.mv, "fraud_signal_rate", 0.40)
        self.assertEqual(RetrainRequest.objects.count(), 1)

    def test_different_metrics_create_separate_requests(self):
        record_drift_metric(self.mv, "fraud_signal_rate", 0.35)
        record_drift_metric(self.mv, "review_trust_avg", 30.0)
        self.assertEqual(RetrainRequest.objects.count(), 2)

    def test_metric_stores_correct_fields(self):
        record_drift_metric(self.mv, "fraud_signal_rate", 0.10)
        metric = DriftMetric.objects.first()
        self.assertEqual(metric.model_version, self.mv)
        self.assertEqual(metric.metric_name, "fraud_signal_rate")
        self.assertAlmostEqual(metric.value, 0.10)
        self.assertEqual(metric.baseline_value, 0.10)
        self.assertEqual(metric.threshold_max, 0.30)


class CheckAllDriftTests(TestCase):
    def test_no_models_creates_default(self):
        self.assertEqual(ModelVersion.objects.count(), 0)
        result = check_all_drift()
        self.assertEqual(ModelVersion.objects.count(), 1)
        self.assertGreater(result["metrics_computed"], 0)

    def test_with_active_model(self):
        ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
        result = check_all_drift()
        self.assertEqual(result["metrics_computed"], 3)  # 3 metrics

    def test_breach_detected(self):
        # Mock the metric functions to force a breach
        with (
            patch("fraud.services.model_monitor.compute_fraud_signal_rate", return_value=0.35),
            patch("fraud.services.model_monitor.compute_review_trust_avg", return_value=70.0),
            patch(
                "fraud.services.model_monitor.compute_photo_geo_mismatch_rate", return_value=0.05
            ),
        ):
            ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
            result = check_all_drift()
            self.assertEqual(result["breaches"], 1)

    def test_all_within_bounds(self):
        with (
            patch("fraud.services.model_monitor.compute_fraud_signal_rate", return_value=0.05),
            patch("fraud.services.model_monitor.compute_review_trust_avg", return_value=75.0),
            patch(
                "fraud.services.model_monitor.compute_photo_geo_mismatch_rate", return_value=0.03
            ),
        ):
            ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
            result = check_all_drift()
            self.assertEqual(result["breaches"], 0)


class AdminAlertTests(TestCase):
    def test_alert_admins_called_on_breach(self):
        with patch("fraud.services.model_monitor.compute_fraud_signal_rate", return_value=0.50):
            ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
            with patch("fraud.services.model_monitor._alert_admins") as mock_alert:
                check_all_drift()
                mock_alert.assert_called_once()


class CeleryTaskTests(TestCase):
    def test_check_model_drift_task(self):
        from fraud.tasks import check_model_drift

        with patch("fraud.services.model_monitor.check_all_drift") as mock:
            mock.return_value = {"metrics_computed": 3, "breaches": 0, "details": []}
            result = check_model_drift()
            mock.assert_called_once()
            self.assertEqual(result["metrics_computed"], 3)

    def test_check_model_drift_task_real(self):
        from fraud.tasks import check_model_drift

        ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
        result = check_model_drift()
        self.assertIn("metrics_computed", result)
        self.assertGreater(result["metrics_computed"], 0)


class AdminAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="test12345",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)
        self.mv = ModelVersion.objects.create(**ACTIVE_MODEL_DATA)

    def test_run_drift_check(self):
        resp = self.client.post("/api/v1/ml/drift/check/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics_computed", resp.json())

    def test_create_drift_metric(self):
        now = timezone.now()
        resp = self.client.post(
            "/api/v1/ml/drift/",
            {
                "model_version": self.mv.pk,
                "metric_name": "accuracy",
                "value": 0.85,
                "window_start": now.isoformat(),
                "window_end": now.isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(DriftMetric.objects.count(), 1)

    def test_create_retrain_request(self):
        resp = self.client.post(
            "/api/v1/ml/retrain/",
            {
                "model_version": self.mv.pk,
                "reason": "Scheduled retrain",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        rr = RetrainRequest.objects.first()
        self.assertEqual(rr.triggered_by, self.admin)

    def test_non_admin_rejected(self):
        user = User.objects.create_user(
            username="regular", email="reg@test.com", password="test12345"
        )
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/v1/ml/drift/check/")
        self.assertEqual(resp.status_code, 403)

    def test_drift_list_filtered(self):
        DriftMetric.objects.create(
            model_version=self.mv,
            metric_name="accuracy",
            value=0.80,
            threshold_breached=True,
            window_start=timezone.now(),
            window_end=timezone.now(),
        )
        resp = self.client.get("/api/v1/ml/drift/?breached=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_retrain_list(self):
        RetrainRequest.objects.create(model_version=self.mv, reason="test")
        resp = self.client.get("/api/v1/ml/retrain/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)


class DriftMetricModelTests(TestCase):
    def test_str_breached(self):
        mv = ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
        dm = DriftMetric.objects.create(
            model_version=mv,
            metric_name="accuracy",
            value=0.80,
            threshold_breached=True,
            window_start=timezone.now(),
            window_end=timezone.now(),
        )
        self.assertIn("BREACHED", str(dm))

    def test_str_ok(self):
        mv = ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
        dm = DriftMetric.objects.create(
            model_version=mv,
            metric_name="accuracy",
            value=0.80,
            window_start=timezone.now(),
            window_end=timezone.now(),
        )
        self.assertIn("ok", str(dm))


class RetrainRequestModelTests(TestCase):
    def test_str_with_model(self):
        mv = ModelVersion.objects.create(**ACTIVE_MODEL_DATA)
        rr = RetrainRequest.objects.create(model_version=mv, reason="Drift")
        self.assertIn("fraud_system", str(rr))

    def test_str_without_model(self):
        rr = RetrainRequest.objects.create(reason="New model")
        self.assertIn("new-model", str(rr))


class Stage2StubTestsUpdated(TestCase):
    """Ensure the old Stage 2 stub tests still pass with real implementation."""

    def test_check_model_drift_is_no_longer_stub(self):
        from fraud.tasks import check_model_drift

        result = check_model_drift()
        self.assertNotEqual(result.get("status"), "stub")

    def test_drift_metric_list_endpoint_works(self):
        client = APIClient()
        admin = User.objects.create_user(
            username="admin2",
            email="admin2@test.com",
            password="test12345",
            is_staff=True,
        )
        client.force_authenticate(user=admin)
        resp = client.get("/api/v1/ml/drift/")
        self.assertEqual(resp.status_code, 200)
