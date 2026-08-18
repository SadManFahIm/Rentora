"""Tests for the Smart AI Alerts prioritization (Tier 4)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .smart_alerts import priority_for, rank_alerts
from .utils import create_notification

User = get_user_model()


class SmartAlertPriorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sa_user", email="sa_user@example.com", password="test12345"
        )

    def test_fraud_outranks_booking(self):
        fraud = create_notification(self.user, "fraud_flag", "Flag", "Suspicious message", meta={})
        booking = create_notification(self.user, "booking_request", "Request", "New booking")
        ranked = rank_alerts([booking, fraud])
        self.assertEqual(ranked[0]["id"], fraud.id)
        self.assertGreater(ranked[0]["priority"], ranked[1]["priority"])

    def test_highly_relevant_match_boosted(self):
        weak = create_notification(
            self.user, "saved_search_match", "Match", "A new room", meta={"level": "ok"}
        )
        strong = create_notification(
            self.user,
            "saved_search_match",
            "Match",
            "A new room",
            meta={"level": "highly_relevant"},
        )
        score_weak, _ = priority_for(weak)
        score_strong, _ = priority_for(strong)
        self.assertGreater(score_strong, score_weak)

    def test_recent_boost(self):
        old = create_notification(self.user, "system", "Old", "Old")
        old.created_at = timezone.now() - timedelta(days=2)
        old.save(update_fields=["created_at"])
        fresh = create_notification(self.user, "system", "Fresh", "Fresh")
        score_old, _ = priority_for(old)
        score_fresh, _ = priority_for(fresh)
        self.assertGreater(score_fresh, score_old)


class SmartAlertEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sa_ep", email="sa_ep@example.com", password="test12345"
        )

    def test_endpoint_returns_ranked(self):
        self.client.force_authenticate(self.user)
        create_notification(self.user, "booking_request", "Request", "New booking")
        resp = self.client.get("/api/v1/notifications/smart/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("alerts", resp.data)
        self.assertEqual(len(resp.data["alerts"]), 1)
        self.assertIn("priority", resp.data["alerts"][0])
        self.assertIn("reason", resp.data["alerts"][0])

    def test_requires_auth(self):
        resp = self.client.get("/api/v1/notifications/smart/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
