"""Tests for the AI Property Comparison (Tier 4) — engine + endpoint."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from pricing.models import MarketStat
from rooms.compare import compare_rooms
from rooms.models import Room

User = get_user_model()


def make_room(owner, title, price, area="Dhanmondi", room_type="studio", size=320, **kw):
    defaults = dict(
        description="A furnished studio with attached bath.",
        room_type=room_type,
        price=price,
        area=area,
        address="Road 6, Dhanmondi",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi", "furnished"],
        size_sqft=size,
        verified=True,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, title=title, **defaults)


class CompareEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="cmp_owner", email="cmp_owner@example.com", password="test12345"
        )
        self.r1 = make_room(self.owner, "Studio A", 12000, size=300)
        self.r2 = make_room(self.owner, "Studio B", 18000, size=400)

    def test_matrix_columns(self):
        out = compare_rooms([self.r1, self.r2])
        self.assertEqual(out["summary"]["count"], 2)
        self.assertEqual(len(out["rooms"]), 2)
        self.assertIn("price_per_sqft", out["columns"])
        self.assertEqual(out["columns"]["price"]["values"][self.r1.id], 12000)
        self.assertEqual(out["rooms"][0]["price_per_sqft"], 40.0)

    def test_cheapest_summary(self):
        out = compare_rooms([self.r1, self.r2])
        self.assertEqual(out["summary"]["cheapest"]["id"], self.r1.id)

    def test_market_position_with_stat(self):
        MarketStat.objects.create(
            area="Dhanmondi",
            room_type="studio",
            avg_price=15000,
            median_price=14500,
            min_price=10000,
            max_price=20000,
            percentile_25=12000,
            percentile_75=17000,
            sample_size=12,
        )
        out = compare_rooms([self.r1, self.r2])
        by_id = {r["id"]: r for r in out["rooms"]}
        self.assertEqual(by_id[self.r1.id]["market_position"], "Below median")
        self.assertEqual(by_id[self.r2.id]["market_position"], "Above median")


class CompareEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="cmp_ep", email="cmp_ep@example.com", password="test12345"
        )
        self.r1 = make_room(self.owner, "Studio A", 12000)
        self.r2 = make_room(self.owner, "Studio B", 18000)

    def test_compare_endpoint(self):
        resp = self.client.get(f"/api/v1/rooms/compare/?ids={self.r1.id},{self.r2.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["summary"]["count"], 2)

    def test_requires_two_ids(self):
        resp = self.client.get(f"/api/v1/rooms/compare/?ids={self.r1.id}")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_too_many_ids(self):
        resp = self.client.get("/api/v1/rooms/compare/?ids=1,2,3,4,5,6")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
