"""Tests for the AI pricing suggestion v2 (Phase 11 — Pricing Intelligence).

Covers: price range/recommendation, demand score, time-to-rent estimation,
confidence, explainable reasons, insufficient-data handling, caching, and
the endpoint's owner/admin permission gate.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking
from pricing.models import MarketStat
from pricing.services.suggestion import (
    _demand_label,
    _demand_score,
    get_pricing_suggestion,
)
from rooms.models import Room, RoomView
from wishlist.models import Wishlist

User = get_user_model()


def make_user(username, nid_verified=True, is_staff=False):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        nid_verified=nid_verified,
        is_staff=is_staff,
    )


def make_room(owner, title="Room", area="Mirpur", room_type="single", price=8000, size=250):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A well-written description with enough words to score well.",
        room_type=room_type,
        price=price,
        area=area,
        address="12 Road, Mirpur",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi", "furnished"],
        size_sqft=size,
    )


def make_stat(area="Mirpur", room_type="single", avg=8500):
    MarketStat.objects.create(
        area=area,
        room_type=room_type,
        avg_price=avg,
        median_price=avg,
        min_price=5000,
        max_price=12000,
        percentile_25=7000,
        percentile_75=10000,
        sample_size=20,
    )


class PricingSuggestionServiceTests(TestCase):
    def setUp(self):
        self.owner = make_user("price_owner")
        # Enough rooms for the Ridge model to train (MIN_ROOMS = 10).
        for i in range(12):
            make_room(self.owner, title=f"Seed Room {i}", price=8000 + i * 500)
        make_stat()
        cache.clear()

    def test_suggestion_shape_and_rounding(self):
        room = make_room(self.owner, "Target Room", price=8000)
        s = get_pricing_suggestion(room)
        self.assertEqual(s["room_id"], room.pk)
        self.assertIsNotNone(s["recommended_price"])
        self.assertIsNotNone(s["min_price"])
        self.assertIsNotNone(s["max_price"])
        # Rounded to 500 BDT granularity.
        for key in ("min_price", "recommended_price", "max_price"):
            self.assertEqual(s[key] % 500, 0, f"{key} not rounded: {s[key]}")
        self.assertGreaterEqual(s["confidence"], 0.0)
        self.assertLessEqual(s["confidence"], 1.0)
        self.assertIn("reasons", s)
        self.assertTrue(s["reasons"])

    def test_range_contains_recommendation(self):
        room = make_room(self.owner, "Target Room", price=8000)
        s = get_pricing_suggestion(room)
        self.assertLessEqual(s["min_price"], s["recommended_price"])
        self.assertLessEqual(s["recommended_price"], s["max_price"])

    def test_demand_score_bounds(self):
        room = make_room(self.owner, "Target Room", price=8000)
        score, raw = _demand_score(room)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        self.assertEqual(raw["room_views_30d"], 0)
        # Add engagement: views + wishlist + booking request push the score up.
        user = make_user("seeker")
        RoomView.objects.create(room=room, viewer=user)
        Wishlist.objects.create(room=room, user=user)
        Booking.objects.create(
            room=room,
            tenant=user,
            check_in=timezone.localdate(),
            monthly_rent=room.price,
        )
        score2, _ = _demand_score(room)
        self.assertGreater(score2, score)

    def test_demand_label_bands(self):
        self.assertEqual(_demand_label(90), "Very High")
        self.assertEqual(_demand_label(70), "High")
        self.assertEqual(_demand_label(40), "Moderate")
        self.assertEqual(_demand_label(10), "Low")

    def test_time_to_rent_insufficient_data(self):
        room = make_room(self.owner, "Target Room", price=8000)
        s = get_pricing_suggestion(room)
        self.assertFalse(s["time_to_rent"]["available"])

    def test_time_to_rent_with_history(self):
        tenant = make_user("tenant")
        # A few older approved bookings in the same area give samples.
        base = make_room(self.owner, "Historic Room", area="Mirpur", price=8000)
        for _ in range(6):
            b = Booking.objects.create(
                room=base,
                tenant=tenant,
                check_in=timezone.localdate(),
                monthly_rent=base.price,
            )
            Booking.objects.filter(pk=b.pk).update(status=Booking.Status.APPROVED)
        target = make_room(self.owner, "Target Room", area="Mirpur", price=8000)
        s = get_pricing_suggestion(target)
        self.assertTrue(s["time_to_rent"]["available"])
        self.assertGreaterEqual(s["time_to_rent"]["days_min"], 1)

    def test_reasons_are_calculated(self):
        room = make_room(self.owner, "Target Room", price=8000)
        s = get_pricing_suggestion(room)
        joined = " ".join(s["reasons"]).lower()
        self.assertIn("mirpur", joined)
        self.assertIn("৳", s["reasons"][0])

    def test_cache_hit_returns_same_payload(self):
        room = make_room(self.owner, "Target Room", price=8000)
        s1 = get_pricing_suggestion(room)
        s2 = get_pricing_suggestion(room)
        self.assertEqual(s1, s2)

    def test_price_change_invalidates_cache(self):
        room = make_room(self.owner, "Target Room", price=8000)
        get_pricing_suggestion(room)  # warm the cache
        room.price = 5000
        room.save()
        s2 = get_pricing_suggestion(room)
        self.assertEqual(s2["current_price"], 5000.0)


class PricingSuggestionViewTests(APITestCase):
    def setUp(self):
        self.owner = make_user("view_owner")
        self.other = make_user("view_other")
        self.admin = make_user("view_admin", is_staff=True)
        for i in range(12):
            make_room(self.owner, title=f"Seed Room {i}", price=8000 + i * 500)
        make_stat()
        self.room = make_room(self.owner, "Target Room", price=8000)

    def test_owner_can_view(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(f"/api/v1/pricing/suggestion/{self.room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["room_id"], self.room.pk)
        self.assertIn("recommended_price", res.data)

    def test_admin_can_view_any(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/pricing/suggestion/{self.room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_other_user_forbidden(self):
        self.client.force_authenticate(user=self.other)
        res = self.client.get(f"/api/v1/pricing/suggestion/{self.room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_forbidden(self):
        res = self.client.get(f"/api/v1/pricing/suggestion/{self.room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
