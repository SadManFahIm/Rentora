"""E2E: the map intelligence flow through the real API (Tier 3 expansion).

Covers the map search -> area stats -> commute ETA chain exactly as the Map
page drives it, including the graceful fallback when the OSRM routing
server is unreachable/disabled (which is the default in CI).
"""

from django.contrib.auth import get_user_model
from django.test import override_settings, tag
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room

User = get_user_model()


def make_room(owner, title, area, price):
    return Room.objects.create(
        owner=owner,
        title=title,
        description=f"{title} near the university with wifi.",
        room_type="single",
        price=price,
        area=area,
        address=f"Somewhere in {area}",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=200,
    )


@tag("e2e")
class MapFlowE2ETest(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="map_landlord",
            email="map_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=True,
        )
        self.uttara = make_room(self.landlord, "Uttara Metro Room", "Uttara", 10000)
        self.mirpur = make_room(self.landlord, "Mirpur Student Room", "Mirpur", 7000)

    def test_map_search_returns_rooms_with_intent(self):
        res = self.client.get("/api/v1/rooms/map-intel/search/?q=Uttara metro")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["rooms"][0]["id"], self.uttara.pk)
        self.assertTrue(res.data["intent"]["areas"])

    def test_area_stats_reflect_listings(self):
        res = self.client.get("/api/v1/rooms/map-intel/stats/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        by_area = {row["area"]: row for row in res.data}
        self.assertEqual(by_area["Uttara"]["listings"], 1)
        self.assertEqual(by_area["Uttara"]["avg_rent"], 10000)
        self.assertEqual(by_area["Mirpur"]["avg_rent"], 7000)

    @override_settings(OSRM_ENABLED=False)
    def test_commute_eta_falls_back_gracefully(self):
        # OSRM off is the safe default; the walking heuristic must still give
        # an estimate instead of an error.
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

    def test_eta_endpoint_rejects_bad_mode(self):
        res = self.client.get(
            "/api/v1/rooms/eta/",
            {"from_lat": "23.8", "from_lng": "90.4", "mode": "rocket"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
