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
