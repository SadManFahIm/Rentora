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


class DhakaHierarchyTests(APITestCase):
    """Phase 7 v3 — structured Dhaka geography (area-hierarchy + geocode merge)."""

    def test_area_hierarchy_returns_main_areas_with_children(self):
        res = self.client.get("/api/v1/rooms/area-hierarchy/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        main_areas = res.data["main_areas"]
        keys = {m["key"] for m in main_areas}
        self.assertIn("uttara", keys)
        self.assertIn("mirpur", keys)
        self.assertIn("dhanmondi", keys)

        uttara = next(m for m in main_areas if m["key"] == "uttara")
        child_keys = {c["key"] for c in uttara["children"]}
        self.assertIn("uttara_sector_7", child_keys)
        self.assertIn("uttara_sector_10", child_keys)
        # Every child points back at its parent main area.
        for child in uttara["children"]:
            self.assertEqual(child["parent"], "uttara")
            self.assertEqual(child["parent_name"], "Uttara")
            self.assertIsInstance(child["lat"], float)
            self.assertIsInstance(child["lng"], float)

    def test_hierarchy_child_kind(self):
        res = self.client.get("/api/v1/rooms/area-hierarchy/")
        uttara = next(m for m in res.data["main_areas"] if m["key"] == "uttara")
        self.assertTrue(all(c["kind"] == "sub_area" for c in uttara["children"]))

    def test_geocode_resolves_sub_area_with_parent(self):
        # "Mirpur 10" must resolve to the structured sub-area, not only the
        # flat gazetteer — and carry its parent district.
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "mirpur 10"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        match = next((s for s in res.data if s["label"] == "Mirpur 10"), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["kind"], "area")
        self.assertEqual(match["parent_name"], "Mirpur")

    def test_geocode_resolves_bangla_alias(self):
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "মিরপুর ১০"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any("Mirpur 10" in s["label"] for s in res.data))

    def test_geocode_still_returns_streets_and_landmarks(self):
        # Hierarchy merge must not break the existing street/landmark flow.
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "gulshan avenue"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(s["kind"] == "street" for s in res.data))

        res = self.client.get("/api/v1/rooms/geocode/", {"q": "mirpur 10"})
        self.assertTrue(any(s["kind"] == "metro" for s in res.data))  # MRT station

    def test_geocode_deduplicates_overlapping_entries(self):
        # The hierarchy and the flat gazetteer both know "Dhanmondi" — the
        # response should contain the key at most once.
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "dhanmondi"})
        keys = [s["key"] for s in res.data]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("dhanmondi", keys)


class AreaBoundaryTests(APITestCase):
    """Phase 7 v3 — approximate area boundary polygons."""

    def test_boundaries_returns_geojson_with_hierarchy_kinds(self):
        res = self.client.get("/api/v1/rooms/area-boundaries/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["type"], "FeatureCollection")
        features = res.data["features"]
        self.assertGreater(len(features), 50)

        kinds = {f["properties"]["kind"] for f in features}
        self.assertEqual(kinds, {"main_area", "sub_area", "neighborhood"})

    def test_polygon_is_closed_and_centered_on_place(self):
        res = self.client.get("/api/v1/rooms/area-boundaries/")
        uttara = next(f for f in res.data["features"] if f["properties"]["key"] == "uttara")
        ring = uttara["geometry"]["coordinates"][0]
        # Closed ring: first == last point.
        self.assertEqual(ring[0], ring[-1])
        # ~2.8 km bubble around Uttara centre (~23.876, 90.380).
        lats = [p[1] for p in ring]
        lngs = [p[0] for p in ring]
        self.assertAlmostEqual((max(lats) + min(lats)) / 2, 23.8759, places=2)
        self.assertAlmostEqual((max(lngs) + min(lngs)) / 2, 90.3795, places=2)
        self.assertAlmostEqual((max(lats) - min(lats)) / 2, 2.8 / 111.32, places=3)
        self.assertEqual(uttara["properties"]["approx_radius_km"], 2.8)

    def test_sub_area_has_smaller_bubble_and_parent(self):
        res = self.client.get("/api/v1/rooms/area-boundaries/")
        mirpur10 = next(f for f in res.data["features"] if f["properties"]["key"] == "mirpur_10")
        self.assertEqual(mirpur10["properties"]["kind"], "sub_area")
        self.assertEqual(mirpur10["properties"]["parent_name"], "Mirpur")
        self.assertEqual(mirpur10["properties"]["approx_radius_km"], 1.4)

    def test_neighborhood_has_smallest_bubble(self):
        res = self.client.get("/api/v1/rooms/area-boundaries/")
        shahbagh = next(f for f in res.data["features"] if f["properties"]["key"] == "shahbagh")
        self.assertEqual(shahbagh["properties"]["kind"], "neighborhood")
        self.assertEqual(shahbagh["properties"]["approx_radius_km"], 0.7)


class ExpandedLandmarkTests(APITestCase):
    """Phase 7 v3 — everyday-places landmark categories."""

    def test_landmarks_endpoint_includes_new_categories(self):
        res = self.client.get("/api/v1/rooms/landmarks/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        kinds = {lm["kind"] for lm in res.data}
        self.assertIn("hospital", kinds)
        self.assertIn("market", kinds)
        self.assertIn("park", kinds)
        self.assertIn("mosque", kinds)
        self.assertIn("bus_terminal", kinds)

    def test_new_categories_have_real_places(self):
        res = self.client.get("/api/v1/rooms/landmarks/")
        by_kind: dict[str, list[dict]] = {}
        for lm in res.data:
            by_kind.setdefault(lm["kind"], []).append(lm)
        self.assertGreaterEqual(len(by_kind["hospital"]), 5)
        self.assertGreaterEqual(len(by_kind["market"]), 5)
        self.assertGreaterEqual(len(by_kind["park"]), 5)
        self.assertGreaterEqual(len(by_kind["mosque"]), 5)
        self.assertGreaterEqual(len(by_kind["bus_terminal"]), 4)
        # Spot-check real places resolve.
        names = {lm["name"] for lm in by_kind["hospital"]}
        self.assertIn("Square Hospital", names)
        names = {lm["name"] for lm in by_kind["mosque"]}
        self.assertIn("Baitul Mukarram National Mosque", names)

    def test_geocode_still_finds_landmarks_across_kinds(self):
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "square hospital"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any("Square Hospital" in s["label"] for s in res.data))

        res = self.client.get("/api/v1/rooms/geocode/", {"q": "baitul mukarram"})
        self.assertTrue(any("Baitul Mukarram" in s["label"] for s in res.data))
