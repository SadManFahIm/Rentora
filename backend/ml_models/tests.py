"""Tests for the ml_models app (Phase 17 — Stage 2)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ml_models.models import DriftMetric, ModelVersion, RetrainRequest

User = get_user_model()


class ModelVersionTests(TestCase):
    def test_create_model_version(self):
        mv = ModelVersion.objects.create(
            name="review_trust",
            version="1.0.0",
            description="Initial trust scoring model.",
            status=ModelVersion.Status.EXPERIMENTAL,
            metrics={"accuracy": 0.85, "f1": 0.82},
        )
        self.assertEqual(mv.name, "review_trust")
        self.assertEqual(mv.status, ModelVersion.Status.EXPERIMENTAL)
        self.assertEqual(mv.metrics["accuracy"], 0.85)

    def test_unique_constraint(self):
        from django.db import IntegrityError

        ModelVersion.objects.create(name="review_trust", version="1.0.0")
        with self.assertRaises(IntegrityError):
            ModelVersion.objects.create(name="review_trust", version="1.0.0")

    def test_same_name_different_version(self):
        ModelVersion.objects.create(name="review_trust", version="1.0.0")
        mv2 = ModelVersion.objects.create(name="review_trust", version="1.1.0")
        self.assertIsNotNone(mv2.pk)

    def test_str(self):
        mv = ModelVersion.objects.create(
            name="photo_geo", version="2.0.0", status=ModelVersion.Status.ACTIVE
        )
        self.assertEqual(str(mv), "photo_geo v2.0.0 [active]")


class DriftMetricTests(TestCase):
    def setUp(self):
        self.mv = ModelVersion.objects.create(name="review_trust", version="1.0.0")

    def test_create_drift_metric(self):
        now = timezone.now()
        dm = DriftMetric.objects.create(
            model_version=self.mv,
            metric_name="accuracy",
            value=0.83,
            baseline_value=0.85,
            threshold_min=0.80,
            window_start=now,
            window_end=now,
            sample_count=1000,
        )
        self.assertAlmostEqual(dm.value, 0.83)
        self.assertFalse(dm.threshold_breached)

    def test_threshold_breached(self):
        now = timezone.now()
        dm = DriftMetric.objects.create(
            model_version=self.mv,
            metric_name="accuracy",
            value=0.75,
            baseline_value=0.85,
            threshold_min=0.80,
            threshold_breached=True,
            window_start=now,
            window_end=now,
        )
        self.assertTrue(dm.threshold_breached)

    def test_related_name(self):
        now = timezone.now()
        DriftMetric.objects.create(
            model_version=self.mv,
            metric_name="f1",
            value=0.80,
            window_start=now,
            window_end=now,
        )
        self.assertEqual(self.mv.drift_metrics.count(), 1)


class RetrainRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin_user", email="admin@example.com", password="test12345"
        )
        self.mv = ModelVersion.objects.create(name="review_trust", version="1.0.0")

    def test_create_retrain_request(self):
        rr = RetrainRequest.objects.create(
            model_version=self.mv,
            reason="Drift detected: accuracy dropped below threshold.",
            triggered_by=self.user,
        )
        self.assertEqual(rr.status, RetrainRequest.Status.PENDING)
        self.assertEqual(rr.triggered_by, self.user)

    def test_str_with_model_version(self):
        rr = RetrainRequest.objects.create(model_version=self.mv, reason="Scheduled retrain.")
        self.assertIn("review_trust", str(rr))

    def test_str_without_model_version(self):
        rr = RetrainRequest.objects.create(reason="Brand-new model training.")
        self.assertIn("new-model", str(rr))
