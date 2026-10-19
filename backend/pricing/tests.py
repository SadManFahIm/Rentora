"""Tests for the price insight and its agreement with the fraud engine."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from fraud.services.detectors import _suspicious_price
from pricing.models import MarketStat
from pricing.services.insight import get_price_insight
from rooms.models import Room

User = get_user_model()


def make_room(price, area="Mirpur", room_type="single"):
    owner = User.objects.create_user(
        username=f"owner_{price}", email=f"owner_{price}@example.com", password="test12345"
    )
    return Room.objects.create(
        owner=owner,
        title="Insight Room",
        description="A room to compare against the market.",
        room_type=room_type,
        price=price,
        area=area,
        address="12 Mirpur Road",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi"],
        size_sqft=250,
    )


class PriceInsightFraudAgreementTests(TestCase):
    def setUp(self):
        MarketStat.objects.create(
            area="Mirpur",
            room_type="single",
            avg_price=8500,
            median_price=8500,
            min_price=5000,
            max_price=12000,
            percentile_25=7000,
            percentile_75=10000,
            sample_size=20,
        )

    def test_low_but_plausible_price_is_a_great_deal(self):
        # 6000 is above the bait floor (0.60 x 7000 = 4200).
        room = make_room(6000)
        insight = get_price_insight(room)
        self.assertIsNotNone(insight)
        self.assertEqual(insight["classification"], "great_deal")
        self.assertIsNone(_suspicious_price(room))

    def test_suspected_bait_price_gets_no_insight(self):
        room = make_room(3000)
        self.assertIsNotNone(_suspicious_price(room))
        self.assertIsNone(get_price_insight(room))

    def test_fair_price_unaffected(self):
        insight = get_price_insight(make_room(8500))
        self.assertEqual(insight["classification"], "fair_price")
