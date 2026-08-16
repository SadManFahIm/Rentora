"""Tests for the self-hosted analytics app (Tier 2)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from analytics.models import Event

User = get_user_model()


class AnalyticsApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="analytics_tenant",
            email="analytics_tenant@example.com",
            password="testpass123",
            role="tenant",
        )
        self.admin = User.objects.create_user(
            username="analytics_admin",
            email="analytics_admin@example.com",
            password="testpass123",
            role="admin",
            is_staff=True,
        )
        self.capture_url = reverse("analytics-capture")
        self.summary_url = reverse("analytics-summary")

    # ---- capture -----------------------------------------------------------

    def test_capture_anonymous_event(self):
        response = self.client.post(
            self.capture_url,
            {"event": "page_view", "session_id": "sess-1", "path": "/rooms"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        event = Event.objects.get(event="page_view")
        self.assertIsNone(event.user)
        self.assertEqual(event.session_id, "sess-1")
        self.assertEqual(event.path, "/rooms")

    def test_capture_authenticated_event_attributes_user(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            self.capture_url,
            {"event": "booking_requested", "properties": {"room_id": 42}},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Event.objects.get().user_id, self.user.pk)

    def test_capture_missing_event_rejected(self):
        response = self.client.post(self.capture_url, {"session_id": "s"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_capture_oversized_properties_rejected(self):
        response = self.client.post(
            self.capture_url,
            {"event": "page_view", "properties": {f"k{i}": "x" for i in range(100)}},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    # ---- summary (admin) ---------------------------------------------------

    def test_summary_requires_admin(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.admin)
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, 200)

    def test_summary_aggregates_and_funnel(self):
        # One tenant reaches page_view twice, then goes on to booking_requested.
        self.client.force_authenticate(self.user)
        self.client.post(self.capture_url, {"event": "page_view", "path": "/rooms"}, format="json")
        self.client.post(self.capture_url, {"event": "page_view", "path": "/rooms"}, format="json")
        self.client.post(self.capture_url, {"event": "booking_requested"}, format="json")
        # One anonymous session for top-page/total counting.
        self.client.force_authenticate(None)
        self.client.post(
            self.capture_url,
            {"event": "page_view", "session_id": "anon", "path": "/rooms"},
            format="json",
        )

        self.client.force_authenticate(self.admin)
        data = self.client.get(self.summary_url, {"days": 7}).data
        self.assertEqual(data["totals"]["events"], 4)
        # Only the anonymous event carries a session_id — one distinct session.
        self.assertEqual(data["totals"]["sessions"], 1)
        # page_view x2 by the tenant + booking_requested x1 by the tenant.
        self.assertEqual(data["totals"]["active_users"], 1)
        # page_view: user fired twice + anon once -> count 3
        top = {e["event"]: e["count"] for e in data["top_events"]}
        self.assertEqual(top["page_view"], 3)
        # funnel: 1 distinct user for page_view (the tenant), 1 for booking.
        self.assertEqual(data["funnel"]["page_view"], 1)
        self.assertEqual(data["funnel"]["booking_requested"], 1)
        self.assertEqual(data["funnel"]["payment_completed"], 0)
        # daily series has one entry.
        self.assertEqual(len(data["daily"]), 1)
