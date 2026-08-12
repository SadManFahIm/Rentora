"""Phase 7 v2 — Intelligent Map tests.

Covers the map-intelligence engine (``rooms.map_intel``) and its API actions:
area statistics, commute ETA, value scores, affordability, ideal-area ranking
and natural-language map search. Everything asserted comes from real data the
tests seed — no fabricated statistics.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from pricing.models import MarketStat
from rooms.landmarks import METRO_STATIONS
from rooms.map_intel import (
    commute_eta,
    haversine_km,
    metro_access_score,
    parse_map_query,
    value_score,
)
from rooms.models import Room

User = get_user_model()


def make_room(
    owner,
    title="Map Room",
    area="Uttara",
    price=10000,
    room_type="single",
    lat=23.8759,
    lng=90.3795,
    amenities=None,
):
    """Uttara Sector-area rooms by default (near MRT Uttara North)."""
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A calm room near the metro.",
        room_type=room_type,
        price=price,
        area=area,
        address="Road 5",
        lat=lat,
        lng=lng,
        amenities=amenities or ["wifi", "furnished"],
        size_sqft=250,
    )


class ParseMapQueryTests(APITestCase):
    """Unit tests for the NL map-query parser (Bangla / Banglish / English)."""

    def test_bangla_budget_area_and_amenity(self):
        intent = parse_map_query("উত্তরায় ১২ হাজারের মধ্যে furnished room")
        self.assertIn("Uttara", intent["areas"])
        self.assertEqual(intent["budget_max"], 12000)
        self.assertIn("Furnished", intent["amenities"])

    def test_banglish_budget(self):
        intent = parse_map_query("Banani under 15k")
        self.assertIn("Banani", intent["areas"])
        self.assertEqual(intent["budget_max"], 15000)

    def test_bangla_metro_constraint(self):
        intent = parse_map_query("metro er kache room")
        self.assertTrue(intent["metro_walk"])

    def test_word_boundary_prevents_kache_ac_match(self):
        # "kache" contains "ac" — the word-boundary regex must not flag it.
        intent = parse_map_query("metro er kache room")
        self.assertNotIn("AC", intent["amenities"])
        self.assertNotIn("Ac", intent["amenities"])

    def test_pet_friendly_phrase_matches_canonical(self):
        intent = parse_map_query("pet friendly room")
        self.assertIn("Pet Friendly", intent["amenities"])

    def test_unknown_query_is_empty_safe(self):
        intent = parse_map_query("xyz nonsense words")
        self.assertEqual(intent["areas"], [])
        self.assertIsNone(intent["budget_max"])
        self.assertEqual(intent["amenities"], [])
        self.assertFalse(intent["metro_walk"])


class CommuteEtaTests(APITestCase):
    """Walking / driving / transit ETA heuristics (labelled estimates)."""

    def test_walking_estimate_is_positive(self):
        eta = commute_eta(23.8759, 90.3795, 23.7928, 90.4067)  # Uttara -> Motijheel
        self.assertEqual(eta.mode, "walking")
        self.assertTrue(eta.estimate)
        self.assertIsNotNone(eta.minutes)
        self.assertGreater(eta.minutes, 0)
        self.assertIn("estimate", eta.detail.lower())

    def test_driving_is_faster_than_walking(self):
        walk = commute_eta(23.8759, 90.3795, 23.7928, 90.4067, "walking")
        drive = commute_eta(23.8759, 90.3795, 23.7928, 90.4067, "driving")
        self.assertLess(drive.minutes, walk.minutes)

    def test_zero_distance_is_zero_minutes(self):
        eta = commute_eta(23.8, 90.4, 23.8, 90.4, "walking")
        self.assertEqual(eta.minutes, 0)

    def test_transit_between_metro_stations_works(self):
        # Two real MRT Line-6 stations: Uttara North & Motijheel.
        a = METRO_STATIONS[0]
        b = next(s for s in METRO_STATIONS if s.name != a.name)
        eta = commute_eta(a.lat, a.lng, b.lat, b.lng, "transit")
        self.assertEqual(eta.mode, "transit")
        self.assertTrue(eta.estimate)
        self.assertIsNotNone(eta.minutes)
        self.assertGreater(eta.minutes, 0)
        self.assertIn("MRT", eta.detail)

    def test_transit_outside_corridor_is_honest(self):
        # Far-away pair (e.g. Uttara -> Khulna) — no MRT corridor available.
        eta = commute_eta(23.8759, 90.3795, 22.8167, 89.5642, "transit")
        self.assertIsNone(eta.minutes)
        self.assertFalse(eta.estimate)
        self.assertIn("unavailable", eta.detail.lower())


class MetroAccessScoreTests(APITestCase):
    def test_station_location_scores_high(self):
        station = METRO_STATIONS[0]
        self.assertGreaterEqual(metro_access_score(station.lat, station.lng), 90)

    def test_far_location_scores_low(self):
        # Far from any Dhaka MRT station.
        self.assertLessEqual(metro_access_score(22.8, 89.5), 20)

    def test_score_is_bounded(self):
        for lat, lng in [(23.8, 90.4), (23.7, 90.3), (23.9, 90.5)]:
            score = metro_access_score(lat, lng)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


class AreaIntelApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="map_landlord", email="map_landlord@example.com", password="test12345"
        )
        self.uttara = make_room(self.landlord, "Uttara A", price=9000, area="Uttara")
        make_room(self.landlord, "Uttara B", price=12000, area="Uttara")
        make_room(self.landlord, "Mirpur C", price=7000, area="Mirpur")

    def test_map_intel_aggregates_areas(self):
        res = self.client.get("/api/v1/rooms/map-intel/stats/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        by_area = {row["area"]: row for row in res.data}
        self.assertIn("Uttara", by_area)
        uttara = by_area["Uttara"]
        self.assertEqual(uttara["listings"], 2)
        self.assertEqual(uttara["avg_rent"], 10500)
        self.assertEqual(uttara["median_rent"], 10500)
        self.assertEqual(uttara["available"], 2)
        self.assertIn("demand", uttara)
        self.assertIn("metro_access", uttara)
        self.assertIn("lat", uttara)
        self.assertIsNotNone(uttara["lat"])

    def test_map_intel_single_area_filter(self):
        res = self.client.get("/api/v1/rooms/map-intel/stats/?area=Mirpur")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["area"], "Mirpur")
        self.assertEqual(res.data[0]["avg_rent"], 7000)

    def test_map_intel_unknown_area_is_empty(self):
        res = self.client.get("/api/v1/rooms/map-intel/stats/?area=Nowhereville")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, [])


class CommuteApiTests(APITestCase):
    def test_walking_mode(self):
        res = self.client.get(
            "/api/v1/rooms/map-intel/commute/",
            {
                "from_lat": 23.8759,
                "from_lng": 90.3795,
                "to_lat": 23.7928,
                "to_lng": 90.4067,
                "mode": "walking",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["mode"], "walking")
        self.assertIsNotNone(res.data["minutes"])
        self.assertTrue(res.data["estimate"])

    def test_missing_params_400(self):
        res = self.client.get("/api/v1/rooms/map-intel/commute/", {"from_lat": "23.8"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_mode_400(self):
        res = self.client.get(
            "/api/v1/rooms/map-intel/commute/",
            {
                "from_lat": "23.8",
                "from_lng": "90.4",
                "to_lat": "23.8",
                "to_lng": "90.41",
                "mode": "teleport",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class ValueScoreApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="value_landlord", email="value_landlord@example.com", password="test12345"
        )
        MarketStat.objects.create(
            area="Uttara",
            room_type="single",
            avg_price=10000,
            median_price=10000,
            min_price=9000,
            max_price=12000,
            percentile_25=9500,
            percentile_75=11000,
            sample_size=2,
        )
        self.room = make_room(self.landlord, "Good Value Room", price=10000, area="Uttara")

    def test_value_score_is_bounded_and_explainable(self):
        score = value_score(self.room)
        self.assertGreaterEqual(score["score"], 0)
        self.assertLessEqual(score["score"], 100)
        self.assertEqual(
            set(score["factors"].keys()),
            {"price_fit", "amenities", "quality", "verified", "demand", "metro"},
        )
        self.assertEqual(score["price_vs_market_pct"], 0.0)

    def test_map_value_api_returns_per_room(self):
        res = self.client.get(f"/api/v1/rooms/map-intel/value/?ids={self.room.pk}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(self.room.pk, res.data)
        self.assertIn("score", res.data[self.room.pk])
        self.assertIn("factors", res.data[self.room.pk])

    def test_map_value_unknown_ids_ignored(self):
        res = self.client.get("/api/v1/rooms/map-intel/value/?ids=999999")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, {})


class AffordabilityApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="aff_landlord", email="aff_landlord@example.com", password="test12345"
        )
        make_room(self.landlord, "Cheap A", price=6000, area="Mirpur")
        make_room(self.landlord, "Mid B", price=12000, area="Mirpur")
        make_room(self.landlord, "Pricey C", price=20000, area="Banani")

    def test_budget_percentages_are_real_shares(self):
        res = self.client.get("/api/v1/rooms/map-intel/affordability/?budget=10000")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        by_area = {row["area"]: row for row in res.data}
        # Mirpur: 1 of 2 within 10k -> 50%
        self.assertEqual(by_area["Mirpur"]["percent"], 50)
        # Banani: 0 of 1 -> 0%
        self.assertEqual(by_area["Banani"]["percent"], 0)

    def test_invalid_budget_400(self):
        res = self.client.get("/api/v1/rooms/map-intel/affordability/?budget=abc")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.get("/api/v1/rooms/map-intel/affordability/?budget=0")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class IdealAreasApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ideal_landlord", email="ideal_landlord@example.com", password="test12345"
        )
        self.uttara = make_room(self.landlord, "Ideal Uttara", price=9000, area="Uttara")
        make_room(self.landlord, "Ideal Mirpur", price=7000, area="Mirpur")
        make_room(self.landlord, "Ideal Banani", price=25000, area="Banani")

    def test_ideal_areas_rank_budget_fit(self):
        res = self.client.get("/api/v1/rooms/map-intel/ideal-areas/?budget=10000")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res.data), 0)
        by_area = {row["area"]: row for row in res.data}
        # Mirpur + Uttara both fully fit a 10k budget; Banani (25k) fits 0%.
        self.assertEqual(by_area["Mirpur"]["affordability_pct"], 100)
        self.assertEqual(by_area["Uttara"]["affordability_pct"], 100)
        self.assertEqual(by_area["Banani"]["affordability_pct"], 0)
        # Ranked best-to-worst by the same score.
        scores = [row["score"] for row in res.data]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # Banani can never outrank a fully-affordable area for this budget.
        self.assertGreater(by_area["Mirpur"]["score"], by_area["Banani"]["score"])
        reasons = res.data[0]["reasons"]
        self.assertTrue(any("fit your" in r for r in reasons))

    def test_ideal_areas_with_destination(self):
        station = METRO_STATIONS[0]
        res = self.client.get(
            "/api/v1/rooms/map-intel/ideal-areas/",
            {
                "budget": 15000,
                "work_lat": station.lat,
                "work_lng": station.lng,
                "max_commute": 30,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res.data), 0)

    def test_ideal_areas_invalid_budget_400(self):
        res = self.client.get("/api/v1/rooms/map-intel/ideal-areas/?budget=-5")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class MapSearchApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="search_landlord", email="search_landlord@example.com", password="test12345"
        )
        self.furnished = make_room(
            self.landlord,
            "Furnished Uttara",
            price=9500,
            area="Uttara",
            amenities=["wifi", "furnished", "ac"],
        )
        make_room(
            self.landlord,
            "Plain Banani",
            price=18000,
            area="Banani",
            amenities=["wifi"],
        )

    def test_bangla_query_filters(self):
        res = self.client.get(
            "/api/v1/rooms/map-intel/search/", {"q": "উত্তরায় ১২ হাজারের মধ্যে furnished room"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["rooms"][0]["id"], self.furnished.pk)
        intent = res.data["intent"]
        self.assertIn("Uttara", intent["areas"])
        self.assertEqual(intent["budget_max"], 12000)

    def test_empty_query_is_safe(self):
        res = self.client.get("/api/v1/rooms/map-intel/search/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 0)
        self.assertEqual(res.data["rooms"], [])

    def test_metro_walk_sets_target(self):
        res = self.client.get(
            "/api/v1/rooms/map-intel/search/", {"q": "metro er kache furnished room"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["intent"]["metro_walk"])
        # Target should resolve to a metro station (a real landmark).
        self.assertIsNotNone(res.data["target"])
        self.assertEqual(res.data["target"]["kind"], "metro")
        self.assertIn("lat", res.data["target"])

    def test_room_type_filter(self):
        make_room(self.landlord, "Studio Flat", price=14000, area="Uttara", room_type="studio")
        res = self.client.get("/api/v1/rooms/map-intel/search/", {"q": "Uttara studio"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["rooms"][0]["room_type"], "studio")


class HaversineUnitTests(APITestCase):
    def test_known_distance_uttara_to_motijheel(self):
        # ~16 km straight-line between Uttara and Motijheel.
        km = haversine_km(23.8759, 90.3795, 23.7331, 90.4150)
        self.assertGreater(km, 14)
        self.assertLess(km, 18)

    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_km(23.8, 90.4, 23.8, 90.4), 0.0, places=6)
