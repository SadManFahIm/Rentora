"""Tests for the demand forecasting engine (Tier 4)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room
from wishlist.models import Wishlist

from .forecast import area_demand, area_demand_summary

User = get_user_model()


def make_room(owner, area="Uttara"):
    return Room.objects.create(
        owner=owner,
        title="Bright room",
        description="A furnished room near the station.",
        room_type="single",
        price=12000,
        area=area,
        address="Sector 7, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=250,
        verified=True,
    )


class ForecastEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="fc_owner", email="fc_owner@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="fc_tenant", email="fc_tenant@example.com", password="test12345"
        )
        self.room = make_room(self.owner, "Uttara")

    def test_insufficient_data_is_honest(self):
        out = area_demand("Uttara")
        self.assertIsNone(out["demand_index"])
        self.assertIn("note", out)

    def test_demand_index_from_signals(self):
        now = timezone.now()
        # Unique (user, room) per wishlist row — use distinct rooms.
        rooms = [make_room(self.owner, "Uttara") for _ in range(6)]
        for i, room in enumerate(rooms):
            Wishlist.objects.create(user=self.tenant, room=room, created_at=now - timedelta(days=i))
        out = area_demand("Uttara")
        self.assertIsNotNone(out["demand_index"])
        self.assertGreaterEqual(out["demand_index"], 0)
        self.assertLessEqual(out["demand_index"], 100)

    def test_summary_lists_areas(self):
        make_room(self.owner, "Mirpur")
        out = area_demand_summary()
        self.assertIn("areas", out)
        self.assertIn("rising", out)
        self.assertIn("falling", out)


class ForecastEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="fc_ep", email="fc_ep@example.com", password="test12345"
        )
        make_room(self.owner, "Uttara")

    def test_area_forecast_endpoint(self):
        resp = self.client.get("/api/v1/analytics/forecast/?area=Uttara")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["area"], "Uttara")

    def test_summary_endpoint(self):
        resp = self.client.get("/api/v1/analytics/forecast/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("areas", resp.data)
