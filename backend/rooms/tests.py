from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .geo import BoundingBox, haversine_km, landmarks_within, nearest_landmark
from .landmarks import METRO_STATIONS, UNIVERSITIES, get_landmark
from .models import Room

User = get_user_model()


class GeoUtilTests(APITestCase):
    def test_haversine_known_distance(self):
        # Dhaka University (~23.734, 90.393) to Mirpur 10 MRT (~23.807, 90.369)
        # is roughly 8.5 km apart; allow a little slack for rounded coords.
        km = haversine_km(23.7340, 90.3929, 23.8069, 90.3687)
        self.assertAlmostEqual(km, 8.5, delta=1.0)

    def test_haversine_zero_for_same_point(self):
        self.assertEqual(haversine_km(23.7, 90.4, 23.7, 90.4), 0.0)

    def test_bbox_parse_valid(self):
        box = BoundingBox.parse("90.35,23.72,90.42,23.83")
        self.assertEqual(
            (box.min_lng, box.min_lat, box.max_lng, box.max_lat),
            (90.35, 23.72, 90.42, 23.83),
        )

    def test_bbox_parse_rejects_wrong_arity(self):
        with self.assertRaises(ValueError):
            BoundingBox.parse("90.35,23.72,90.42")

    def test_bbox_parse_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            BoundingBox.parse("a,b,c,d")

    def test_bbox_parse_rejects_inverted(self):
        with self.assertRaises(ValueError):
            BoundingBox.parse("90.42,23.83,90.35,23.72")

    def test_nearest_landmark_picks_closest(self):
        # A point sitting on top of Mirpur 10 must resolve to it.
        landmark, distance = nearest_landmark(23.8069, 90.3687, METRO_STATIONS)
        self.assertEqual(landmark.key, "mrt_mirpur_10")
        self.assertLess(distance, 0.5)

    def test_landmarks_within_is_sorted_and_bounded(self):
        results = landmarks_within(23.7340, 90.3929, 2.0, UNIVERSITIES)
        self.assertTrue(all(dist <= 2.0 for _, dist in results))
        self.assertEqual(results, sorted(results, key=lambda pair: pair[1]))

    def test_get_landmark_unknown_returns_none(self):
        self.assertIsNone(get_landmark("does_not_exist"))


class RoomGeoAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="landlord", email="l@example.com", password="pw12345!"
        )
        # Two Mirpur rooms (near Mirpur 10 MRT) and one Dhanmondi room (near DU).
        cls.mirpur_a = cls._room("Mirpur A", "Mirpur", 23.8069, 90.3687)
        cls.mirpur_b = cls._room("Mirpur B", "Mirpur", 23.8180, 90.3654)
        cls.dhanmondi = cls._room("Dhanmondi One", "Dhanmondi", 23.7461, 90.3742)

    @classmethod
    def _room(cls, title, area, lat, lng):
        return Room.objects.create(
            title=title,
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=area,
            address="somewhere",
            lat=lat,
            lng=lng,
            size_sqft=200,
            owner=cls.owner,
        )

    def test_list_includes_proximity(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.status_code, 200)
        room = res.data["results"][0]
        self.assertIn("proximity", room)
        self.assertIn("nearest_university", room["proximity"])
        self.assertIn("nearest_metro", room["proximity"])
        self.assertIsNone(room["distance_km"])  # no reference point in this query

    def test_landmarks_endpoint(self):
        res = self.client.get("/api/v1/rooms/landmarks/")
        self.assertEqual(res.status_code, 200)
        keys = {lm["key"] for lm in res.data}
        self.assertIn("du", keys)
        self.assertIn("mrt_mirpur_10", keys)

    def test_bbox_filters_to_viewport(self):
        # A tight box around Mirpur should exclude the Dhanmondi room.
        res = self.client.get("/api/v1/rooms/?bbox=90.36,23.80,90.37,23.82")
        titles = {r["title"] for r in res.data["results"]}
        self.assertIn("Mirpur A", titles)
        self.assertNotIn("Dhanmondi One", titles)

    def test_invalid_bbox_returns_400(self):
        res = self.client.get("/api/v1/rooms/?bbox=1,2,3")
        self.assertEqual(res.status_code, 400)

    def test_radius_and_distance_and_ordering_via_near_landmark(self):
        # Rooms within 3 km of Mirpur 10 MRT, nearest first, each annotated.
        res = self.client.get("/api/v1/rooms/?near_landmark=mrt_mirpur_10&radius_km=3")
        titles = [r["title"] for r in res.data["results"]]
        self.assertIn("Mirpur A", titles)
        self.assertNotIn("Dhanmondi One", titles)  # ~8 km away, excluded
        # Mirpur A is right on the station, so it must sort ahead of Mirpur B.
        self.assertEqual(titles[0], "Mirpur A")
        first = res.data["results"][0]
        self.assertIsNotNone(first["distance_km"])
        self.assertLess(first["distance_km"], 0.5)

    def test_unknown_near_landmark_returns_400(self):
        res = self.client.get("/api/v1/rooms/?near_landmark=nope&radius_km=2")
        self.assertEqual(res.status_code, 400)

    def test_near_lat_without_near_lng_returns_400(self):
        res = self.client.get("/api/v1/rooms/?near_lat=23.8")
        self.assertEqual(res.status_code, 400)

    def test_explicit_ordering_overrides_distance_sort(self):
        # With ?ordering=price, price wins even though a reference point exists.
        self.mirpur_b.price = 1
        self.mirpur_b.save()
        res = self.client.get(
            "/api/v1/rooms/?near_landmark=mrt_mirpur_10&radius_km=5&ordering=price"
        )
        self.assertEqual(res.data["results"][0]["title"], "Mirpur B")

    def test_detail_includes_nearby_landmarks(self):
        res = self.client.get(f"/api/v1/rooms/{self.mirpur_a.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("nearby_landmarks", res.data)
        # Mirpur 10 MRT is essentially at this room, so it must be listed.
        nearby_keys = {lm["key"] for lm in res.data["nearby_landmarks"]}
        self.assertIn("mrt_mirpur_10", nearby_keys)


class RoomGeocodeTests(APITestCase):
    def test_geocode_finds_street_by_prefix(self):
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "mirpur road"})
        self.assertEqual(res.status_code, 200)
        labels = [s["label"] for s in res.data]
        self.assertTrue(any("Mirpur Road" in label for label in labels))
        suggestion = next(s for s in res.data if "Mirpur Road" in s["label"])
        self.assertEqual(suggestion["kind"], "street")
        self.assertIsInstance(suggestion["lat"], float)
        self.assertIsInstance(suggestion["lng"], float)

    def test_geocode_finds_area_and_landmark(self):
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "gulshan"})
        labels = [s["label"] for s in res.data]
        self.assertTrue(any("Gulshan" in label for label in labels))
        self.assertTrue(any(s["kind"] == "area" for s in res.data))

        res = self.client.get("/api/v1/rooms/geocode/", {"q": "mirpur 10"})
        self.assertTrue(any("Mirpur 10" in s["label"] for s in res.data))

    def test_geocode_empty_query_returns_empty(self):
        res = self.client.get("/api/v1/rooms/geocode/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])

    def test_geocode_unknown_query_returns_empty(self):
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "zzzznope"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])

    def test_geocode_limits_to_8(self):
        # A broad query like "d" should not return more than 8 suggestions.
        res = self.client.get("/api/v1/rooms/geocode/", {"q": "d"})
        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(len(res.data), 8)

    def test_geocode_falls_back_to_nominatim_on_miss(self):
        from unittest.mock import patch

        hit = {
            "key": "osm-way-123",
            "label": "Indira Road",
            "kind": "street",
            "lat": 23.74,
            "lng": 90.39,
        }
        with patch("rooms.views.nominatim_search", return_value=[hit]) as mock:
            res = self.client.get("/api/v1/rooms/geocode/", {"q": "indira road"})
        self.assertEqual(res.status_code, 200)
        mock.assert_called_once()
        self.assertIn("Indira Road", [s["label"] for s in res.data])

    def test_geocode_skips_nominatim_when_gazetteer_hits(self):
        from unittest.mock import patch

        with patch("rooms.views.nominatim_search") as mock:
            res = self.client.get("/api/v1/rooms/geocode/", {"q": "gulshan avenue"})
        self.assertEqual(res.status_code, 200)
        mock.assert_not_called()
        self.assertTrue(any("Gulshan Avenue" in s["label"] for s in res.data))

    def test_geocode_deduplicates_osm_hits(self):
        from unittest.mock import patch

        hit = {
            "key": "osm-node-7",
            "label": "Mirpur Road",
            "kind": "street",
            "lat": 23.78,
            "lng": 90.37,
        }
        with patch("rooms.views.nominatim_search", return_value=[hit, hit]):
            res = self.client.get("/api/v1/rooms/geocode/", {"q": "mirpur road extra"})
        labels = [s["label"] for s in res.data]
        self.assertEqual(labels.count("Mirpur Road"), 1)


class RoomSummaryAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="summarized", email="sum@example.com", password="pw12345!"
        )
        cls.mirpur = Room.objects.create(
            title="Summary Mirpur",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=7000,
            area="Mirpur",
            address="somewhere",
            lat=23.8069,
            lng=90.3687,
            size_sqft=200,
            owner=cls.owner,
            is_available=False,
        )
        cls.dhanmondi = Room.objects.create(
            title="Summary Dhanmondi",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=11000,
            area="Dhanmondi",
            address="somewhere",
            lat=23.7461,
            lng=90.3742,
            size_sqft=200,
            owner=cls.owner,
            is_available=True,
        )

    def test_summary_counts_all(self):
        res = self.client.get("/api/v1/rooms/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total"], 2)
        self.assertEqual(res.data["available"], 1)
        self.assertEqual(res.data["avg_price"], 9000.0)
        self.assertEqual(res.data["min_price"], 7000.0)
        self.assertEqual(res.data["max_price"], 11000.0)

    def test_summary_by_area_includes_centers_for_known_areas(self):
        res = self.client.get("/api/v1/rooms/summary/")
        row = next(r for r in res.data["by_area"] if r["area"] == "Dhanmondi")
        self.assertEqual(row["count"], 1)
        # The gazetteer knows Dhanmondi's centre, so the chip can fly there.
        self.assertIn("lat", row)
        self.assertIn("lng", row)
        self.assertGreater(row["lat"], 23.7)
        self.assertLess(row["lat"], 23.8)

    def test_summary_respects_bbox(self):
        # A tight box around Mirpur excludes the Dhanmondi room.
        res = self.client.get("/api/v1/rooms/summary/?bbox=90.36,23.80,90.37,23.82")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total"], 1)
        # The Mirpur room is unavailable, so per-area chips exclude it.
        self.assertEqual(res.data["by_area"], [])

    def test_summary_respects_area_filter(self):
        res = self.client.get("/api/v1/rooms/summary/?area=Dhanmondi")
        self.assertEqual(res.data["total"], 1)
        self.assertEqual(res.data["avg_price"], 11000.0)

    def test_summary_respects_radius(self):
        res = self.client.get("/api/v1/rooms/summary/?near_landmark=mrt_mirpur_10&radius_km=3")
        self.assertEqual(res.data["total"], 1)
        # Mirpur room is unavailable — chips only surface bookable areas.
        self.assertEqual(res.data["by_area"], [])

    def test_summary_invalid_bbox_returns_400(self):
        res = self.client.get("/api/v1/rooms/summary/?bbox=bad")
        self.assertEqual(res.status_code, 400)

    def test_summary_empty_area_breakdown(self):
        res = self.client.get("/api/v1/rooms/summary/?area=NoSuchArea")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total"], 0)
        self.assertEqual(res.data["by_area"], [])


class RoomTierAPITests(APITestCase):
    """Paid listing tiers — serialization, ordering, and the catalog."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="tierlandlord", email="t@example.com", password="pw12345!"
        )
        cls.free = cls._room("Free Room", Room.Tier.FREE)
        cls.featured = cls._room("Featured Room", Room.Tier.FEATURED)
        cls.premium = cls._room("Premium Room", Room.Tier.PREMIUM)

    @classmethod
    def _room(cls, title, tier):
        return Room.objects.create(
            title=title,
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="somewhere",
            lat=23.74,
            lng=90.37,
            size_sqft=200,
            owner=cls.owner,
            tier=tier,
            is_featured=tier != Room.Tier.FREE,
        )

    def test_list_exposes_tier_fields(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.status_code, 200)
        for room in res.data["results"]:
            self.assertIn("tier", room)
            self.assertIn("tier_expires_at", room)

    def test_default_ordering_ranks_premium_then_featured_then_free(self):
        res = self.client.get("/api/v1/rooms/")
        titles = [
            r["title"]
            for r in res.data["results"]
            if r["title"] in ("Free Room", "Featured Room", "Premium Room")
        ]
        self.assertEqual(titles, ["Premium Room", "Featured Room", "Free Room"])

    def test_explicit_ordering_overrides_tier_boost(self):
        res = self.client.get("/api/v1/rooms/?ordering=created_at")
        self.assertEqual(res.status_code, 200)

    def test_tier_catalog_public(self):
        res = self.client.get("/api/v1/rooms/tier-catalog/")
        self.assertEqual(res.status_code, 200)
        tiers = {t["tier"] for t in res.data["tiers"]}
        self.assertEqual(tiers, {"free", "featured", "premium"})
        self.assertGreater(res.data["duration_days"], 0)
        self.assertEqual(res.data["currency"], "BDT")

    def test_create_ignores_client_tier(self):
        """Landlords cannot set a paid tier on create — only via payment."""
        self.client.force_authenticate(self.owner)
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": "Hack Tier",
                "description": "test",
                "room_type": "single",
                "price": 8000,
                "area": "Dhanmondi",
                "address": "x",
                "lat": 23.74,
                "lng": 90.37,
                "size_sqft": 200,
                "tier": "premium",
                "is_featured": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        room = Room.objects.get(pk=res.data["id"])
        self.assertEqual(room.tier, Room.Tier.FREE)
        self.assertFalse(room.is_featured)

    def test_owner_filter(self):
        other = User.objects.create_user(
            username="otherlandlord", email="other@example.com", password="pw12345!"
        )
        Room.objects.create(
            title="Other's Room",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="somewhere",
            lat=23.74,
            lng=90.37,
            size_sqft=200,
            owner=other,
        )
        res = self.client.get(f"/api/v1/rooms/?owner={self.owner.id}")
        titles = [r["title"] for r in res.data["results"]]
        self.assertIn("Free Room", titles)
        self.assertNotIn("Other's Room", titles)

    def test_expired_tier_reports_as_free(self):
        from django.utils import timezone

        # A listing whose promotion period has passed must not keep its
        # Premium rank/badge — effective tier falls back to free.
        expired = Room.objects.create(
            title="Expired Premium",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="somewhere",
            lat=23.74,
            lng=90.37,
            size_sqft=200,
            owner=self.owner,
            tier=Room.Tier.PREMIUM,
            is_featured=True,
            tier_expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        res = self.client.get("/api/v1/rooms/")
        room = next(r for r in res.data["results"] if r["id"] == expired.id)
        self.assertEqual(room["tier"], "free")
        self.assertFalse(room["is_featured"])

    def test_expire_listings_command(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        Room.objects.filter(pk=self.premium.pk).update(
            tier_expires_at=timezone.now() - timedelta(days=1)
        )
        call_command("expire_listings")
        self.premium.refresh_from_db()
        self.assertEqual(self.premium.tier, Room.Tier.FREE)
        self.assertFalse(self.premium.is_featured)
        self.assertIsNone(self.premium.tier_expires_at)
