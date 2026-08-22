"""Tests for the self-hosted analytics app (Tier 2 / Phase 16 Stage 8)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from analytics.models import Event
from analytics.tasks import purge_expired_events

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


class AnalyticsTaxonomyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="taxo_tenant",
            email="taxo_tenant@example.com",
            password="testpass123",
            role="tenant",
        )
        self.admin = User.objects.create_user(
            username="taxo_admin",
            email="taxo_admin@example.com",
            password="testpass123",
            role="admin",
            is_staff=True,
        )
        self.capture_url = reverse("analytics-capture")
        self.taxonomy_url = reverse("analytics-taxonomy")

    def test_taxonomy_requires_admin(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(self.taxonomy_url).status_code, 403)

    def test_taxonomy_lists_event_names_with_counts(self):
        self.client.post(self.capture_url, {"event": "page_view", "category": "nav"}, format="json")
        self.client.post(self.capture_url, {"event": "page_view", "category": "nav"}, format="json")
        self.client.post(
            self.capture_url, {"event": "booking_requested", "category": "booking"}, format="json"
        )

        self.client.force_authenticate(self.admin)
        data = self.client.get(self.taxonomy_url).data
        by_name = {row["event"]: row for row in data["events"]}
        self.assertEqual(data["total_events"], 3)
        self.assertEqual(by_name["page_view"]["count"], 2)
        self.assertEqual(by_name["page_view"]["category"], "nav")
        self.assertEqual(by_name["booking_requested"]["count"], 1)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class AnalyticsRetentionTaskTests(TestCase):
    def setUp(self):
        cache.clear()

    def _make_event(self, days_ago: int, event="page_view") -> Event:
        row = Event.objects.create(event=event)
        # auto_now_add ignores an explicit value on create() — backdate via
        # update() so retention logic sees a genuinely old row.
        Event.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return row

    @override_settings(ANALYTICS_EVENT_RETENTION_DAYS=30)
    def test_purge_deletes_events_older_than_retention(self):
        old = self._make_event(90)
        fresh = self._make_event(5)
        result = purge_expired_events()
        self.assertTrue(result["ok"])
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(Event.objects.filter(pk=old.pk).exists())
        self.assertTrue(Event.objects.filter(pk=fresh.pk).exists())

    @override_settings(ANALYTICS_EVENT_RETENTION_DAYS=365)
    def test_purge_keeps_events_within_retention(self):
        self._make_event(30)
        result = purge_expired_events()
        self.assertTrue(result["ok"])
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(Event.objects.count(), 1)
