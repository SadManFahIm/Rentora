"""Tests for Tier-5 per-listing price recommendation (demand + market link).

Key properties:

- Recommendations are grounded: direction comes from area demand, market
  position, and own interest signals — never invented.
- Thin data yields an honest low-confidence suggestion, not a fake number.
- The API endpoint is owner/admin-only (403 for strangers).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from analytics.models import Event
from bookings.models import Booking
from pricing.models import MarketStat
from rooms.models import Room
from rooms.price_recommendation import listing_price_recommendation

User = get_user_model()


def make_room(owner, price=14000, area="Dhanmondi", room_type="single", **kw):
    defaults = dict(
        title="Rec Room",
        description="A test room.",
        room_type=room_type,
        price=price,
        area=area,
        address="Road 6",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi"],
        size_sqft=320,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, **defaults)


class PriceRecommendationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="rec_owner", email="rec_owner@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="rec_tenant", email="rec_tenant@example.com", password="test12345"
        )
        self.other = User.objects.create_user(
            username="rec_other", email="rec_other@example.com", password="test12345"
        )
        self.room = make_room(self.owner)
        MarketStat.objects.create(
            area="Dhanmondi",
            room_type="single",
            avg_price=15000,
            median_price=14500,
            min_price=10000,
            max_price=20000,
            percentile_25=12000,
            percentile_75=17000,
            sample_size=12,
        )

    def _seed_demand(self):
        """Rising-area-demand: more bookings in each recent week."""
        from datetime import date

        # Increasing counts going back → rising linear trend + high index.
        # (2,3,4,5 bookings at 25/18/11/4 days ago)
        offsets: list[tuple[int, int]] = [(25, 2), (18, 3), (11, 4), (4, 5)]
        i = 0
        for days_back, count in offsets:
            for _ in range(count):
                room = make_room(self.owner, title=f"Area Room {i}")
                created = timezone.now() - timedelta(days=days_back)
                Booking.objects.filter(
                    pk=Booking.objects.create(
                        room=room,
                        tenant=self.tenant,
                        check_in=date(2026, 9, 1),
                        monthly_rent=12000,
                    ).pk
                ).update(created_at=created)
                i += 1
        Event.objects.create(
            event="room_view",
            properties={"room_id": self.room.pk, "area": "Dhanmondi"},
            created_at=timezone.now() - timedelta(days=1),
        )

    def test_returns_grounded_payload(self):
        out = listing_price_recommendation(self.room)
        self.assertEqual(out["room_id"], self.room.pk)
        self.assertEqual(out["current_price"], float(self.room.price))
        self.assertIn(out["direction"], ("raise", "hold", "lower"))
        self.assertIn(out["confidence"], ("high", "medium", "low"))
        self.assertIsInstance(out["reasons"], list)

    def test_never_raises_without_market_data(self):
        Room.objects.filter(pk=self.room.pk).update(area="Mirpur")
        self.room.refresh_from_db()
        out = listing_price_recommendation(self.room)
        self.assertEqual(out["direction"], "hold")  # no signals → honest hold
        self.assertIn(out["confidence"], ("low", "medium"))

    def test_rising_demand_can_raise(self):
        self._seed_demand()
        # Push price well below the market median so market + demand agree.
        self.room.price = 9000
        self.room.save()
        out = listing_price_recommendation(self.room)
        self.assertIn(out["direction"], ("raise", "hold"))
        self.assertTrue(any("demand" in r.lower() for r in out["reasons"]))

    def test_above_market_price_suggests_lower(self):
        self.room.price = 26000  # well above 14500 median
        self.room.save()
        out = listing_price_recommendation(self.room)
        self.assertIn(out["direction"], ("lower", "hold"))
        self.assertTrue(any("median" in r.lower() or "market" in r.lower() for r in out["reasons"]))

    def test_endpoint_owner_and_admin_only(self):
        url = f"/api/v1/rooms/{self.room.pk}/price-recommendation/"
        # Anonymous → 403/401 (IsAuthenticated)
        response = self.client.get(url)
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )
        # Other user → 403
        self.client.force_authenticate(self.other)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # Owner → 200
        self.client.force_authenticate(self.owner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["room_id"], self.room.pk)

    # ---- Phase 15 C7 — dynamic pricing v2 ----------------------------------

    def test_v2_shape_and_ttl(self):
        out = listing_price_recommendation(self.room)
        self.assertEqual(out["version"], 2)
        self.assertIn("dynamic_price", out)
        self.assertIn("window", out)
        self.assertIn("valid_until", out)
        self.assertEqual(len(out["drivers"]), 3)
        self.assertEqual(
            {d["factor"] for d in out["drivers"]},
            {"area_demand", "market_position", "interest_velocity"},
        )
        # TTL is ~24h in the future.

        from django.utils.dateparse import parse_datetime

        valid_until = parse_datetime(out["valid_until"])
        self.assertLess(valid_until - timezone.now(), timedelta(hours=25))

    def test_dynamic_price_none_when_nothing_grounded(self):
        Room.objects.filter(pk=self.room.pk).update(area="Mirpur")
        self.room.refresh_from_db()
        out = listing_price_recommendation(self.room)
        self.assertIsNone(out["dynamic_price"])
        self.assertIsNone(out["demand_momentum_pct"])
        # The window still anchors honestly around the current price.
        self.assertEqual(out["window"]["min"] < self.room.price < out["window"]["max"], True)

    def test_window_centered_and_bounded(self):
        out = listing_price_recommendation(self.room)
        center = (out["window"]["min"] + out["window"]["max"]) / 2
        anchor = out["dynamic_price"] or float(self.room.price)
        self.assertAlmostEqual(center, anchor, delta=150)  # ৳100 rounding slack
        self.assertLess(out["window"]["min"], out["window"]["max"])
        self.assertGreaterEqual(
            out["window"]["min"],
            self.room.price * 0.92,  # never beyond ±8%
        )

    def test_dynamic_price_bounded_to_8pct(self):
        self._seed_demand()
        self.room.price = 9000
        self.room.save()
        out = listing_price_recommendation(self.room)
        if out["dynamic_price"] is not None:
            self.assertLessEqual(out["dynamic_price"], 9000 * 1.08)
            self.assertGreaterEqual(out["dynamic_price"], 9000 * 0.92)

    def test_momentum_grounded_when_demand_exists(self):
        self._seed_demand()
        out = listing_price_recommendation(self.room)
        self.assertIsNotNone(out["demand_momentum_pct"])
        self.assertLessEqual(abs(out["demand_momentum_pct"]), 3.0)
