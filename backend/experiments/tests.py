"""Experiment service + API tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from analytics.models import Event

from .models import Experiment, ExperimentExposure, ExperimentVariant
from .services import get_variant, record_conversion, record_exposure

User = get_user_model()


def _make_experiment(**kwargs) -> Experiment:
    defaults = dict(
        key="pricing_card_test",
        name="Pricing card redesign",
        status=Experiment.Status.ACTIVE,
        traffic_allocation=100,
        start_at=timezone.now() - timezone.timedelta(days=1),
        end_at=timezone.now() + timezone.timedelta(days=7),
    )
    defaults.update(kwargs)
    experiment = Experiment.objects.create(**defaults)
    ExperimentVariant.objects.create(
        experiment=experiment, key="control", label="Control", weight=1, is_control=True
    )
    ExperimentVariant.objects.create(
        experiment=experiment, key="variant_b", label="New pricing layout", weight=1
    )
    return experiment


class ExperimentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="exp_user", email="exp_user@example.com", password="test12345"
        )

    def test_assignment_is_deterministic(self):
        _make_experiment()
        v1 = get_variant("pricing_card_test", user=self.user)[1]
        v2 = get_variant("pricing_card_test", user=self.user)[1]
        self.assertEqual(v1, v2)
        self.assertIn(v1.key, ("control", "variant_b"))

    def test_draft_experiment_never_assigns(self):
        _make_experiment(status=Experiment.Status.DRAFT)
        _, variant = get_variant("pricing_card_test", user=self.user)
        self.assertIsNone(variant)

    def test_expired_experiment_never_assigns(self):
        _make_experiment(
            start_at=timezone.now() - timezone.timedelta(days=10),
            end_at=timezone.now() - timezone.timedelta(days=3),
        )
        _, variant = get_variant("pricing_card_test", user=self.user)
        self.assertIsNone(variant)

    def test_traffic_allocation_respected(self):
        _make_experiment(traffic_allocation=0)
        _, variant = get_variant("pricing_card_test", user=self.user)
        self.assertIsNone(variant)

    def test_missing_experiment_returns_none(self):
        experiment, variant = get_variant("no.such.experiment", user=self.user)
        self.assertIsNone(experiment)
        self.assertIsNone(variant)

    def test_anonymous_caller_gets_stable_assignment(self):
        _make_experiment()
        v1 = get_variant("pricing_card_test", anonymous_id="anon-abc")[1]
        v2 = get_variant("pricing_card_test", anonymous_id="anon-abc")[1]
        self.assertEqual(v1, v2)

    def test_exposure_idempotent_per_caller(self):
        _make_experiment()
        variant = get_variant("pricing_card_test", anonymous_id="anon-x")[1]
        first = record_exposure("pricing_card_test", variant.key, anonymous_id="anon-x")
        second = record_exposure("pricing_card_test", variant.key, anonymous_id="anon-x")
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(ExperimentExposure.objects.count(), 1)

    def test_conversion_creates_exposure_and_event(self):
        _make_experiment()
        variant = get_variant("pricing_card_test", user=self.user)[1]
        ok = record_conversion(
            "pricing_card_test",
            variant.key,
            "booking_created",
            user=self.user,
            context={"booking_id": 42},
        )
        self.assertTrue(ok)
        self.assertTrue(Event.objects.filter(event="booking_created").exists())
        event = Event.objects.get(event="booking_created")
        self.assertEqual(event.properties.get("experiment"), "pricing_card_test")
        self.assertEqual(event.properties.get("variant"), variant.key)


class ExperimentApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="exp_api", email="exp_api@example.com", password="test12345"
        )
        self.client.force_authenticate(user=self.user)
        _make_experiment()

    def test_active_experiments_returns_variant(self):
        resp = self.client.get("/api/v1/experiments/active/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        item = resp.data["experiments"][0]
        self.assertEqual(item["key"], "pricing_card_test")
        self.assertIn(item["variant"], ("control", "variant_b"))

    def test_exposure_endpoint(self):
        variant = get_variant("pricing_card_test", user=self.user)[1]
        resp = self.client.post(
            "/api/v1/experiments/exposure/",
            {
                "experiment_key": "pricing_card_test",
                "variant_key": variant.key,
                "context": {"page": "room_detail"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["recorded"])

    def test_conversion_endpoint(self):
        variant = get_variant("pricing_card_test", user=self.user)[1]
        resp = self.client.post(
            "/api/v1/experiments/conversion/",
            {
                "experiment_key": "pricing_card_test",
                "variant_key": variant.key,
                "event_name": "booking_created",
                "context": {"booking_id": 1},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["recorded"])

    def test_conversion_endpoint_validates_event_name(self):
        resp = self.client.post(
            "/api/v1/experiments/conversion/",
            {"experiment_key": "pricing_card_test", "variant_key": "control"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
