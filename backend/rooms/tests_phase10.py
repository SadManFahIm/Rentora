"""Phase 10 room tests — search v2, view tracking, landlord insights, bulk."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room, RoomView

User = get_user_model()


def make_room(owner, title, area="Mirpur", price=9000, room_type="single"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A cozy room near the university.",
        room_type=room_type,
        price=price,
        area=area,
        address="12 Road",
        lat=23.8,
        lng=90.4,
        amenities=["wifi", "furnished"],
        size_sqft=250,
    )


class SearchV2Tests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="slandlord", email="sl@example.com", password="test12345"
        )
        self.room = make_room(self.landlord, "Sunny Studio in Mirpur")
        make_room(self.landlord, "Budget Room in Dhanmondi", area="Dhanmondi", price=6000)

    def test_q_filters_and_matches_area(self):
        res = self.client.get("/api/v1/rooms/?q=mirpur")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["title"], "Sunny Studio in Mirpur")

    def test_q_matches_description(self):
        res = self.client.get("/api/v1/rooms/?q=university")
        self.assertEqual(res.data["count"], 2)

    def test_empty_q_returns_everything(self):
        res = self.client.get("/api/v1/rooms/?q=")
        self.assertEqual(res.data["count"], 2)


class RoomViewTrackingTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="vl", email="vl@example.com", password="test12345"
        )
        self.viewer = User.objects.create_user(
            username="viewer", email="viewer@example.com", password="test12345"
        )
        self.room = make_room(self.landlord, "Tracked Room")

    def test_detail_logs_view_and_dedupes(self):
        self.client.force_authenticate(self.viewer)
        self.client.get(f"/api/v1/rooms/{self.room.pk}/")
        self.client.get(f"/api/v1/rooms/{self.room.pk}/")
        # Deduped within 5 minutes -> exactly one row.
        self.assertEqual(RoomView.objects.filter(room=self.room).count(), 1)

    def test_anonymous_view_is_not_tracked(self):
        self.client.get(f"/api/v1/rooms/{self.room.pk}/")
        self.assertEqual(RoomView.objects.filter(room=self.room).count(), 0)


class LandlordInsightsTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="il", email="il@example.com", password="test12345"
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="test12345"
        )
        self.room = make_room(self.landlord, "Insight Room")
        make_room(self.other, "Not Mine")
        self.client.force_authenticate(self.landlord)

    def test_insights_only_show_own_rooms(self):
        res = self.client.get("/api/v1/rooms/insights/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["rooms"]), 1)
        row = res.data["rooms"][0]
        self.assertEqual(row["title"], "Insight Room")
        self.assertEqual(row["views_30d"], 0)
        self.assertEqual(row["booking_requests"], 0)
        self.assertIn("price_delta_pct", row)
        self.assertEqual(res.data["summary"]["listing_count"], 1)

    def test_insights_requires_auth(self):
        self.client.force_authenticate(None)
        res = self.client.get("/api/v1/rooms/insights/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class BulkCreateTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="bl", email="bl@example.com", password="test12345"
        )
        self.client.force_authenticate(self.landlord)

    def test_bulk_creates_valid_rows_and_reports_errors(self):
        payload = [
            {
                "title": "Bulk One",
                "description": "d",
                "room_type": "single",
                "price": 8000,
                "area": "Mirpur",
                "address": "x",
                "lat": 23.8,
                "lng": 90.4,
                "size_sqft": 200,
            },
            {"title": "Broken", "description": "d"},  # missing required fields
        ]
        res = self.client.post("/api/v1/rooms/bulk/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["created_count"], 1)
        self.assertEqual(len(res.data["errors"]), 1)
        self.assertEqual(Room.objects.filter(owner=self.landlord).count(), 1)

    def test_bulk_requires_list(self):
        res = self.client.post("/api/v1/rooms/bulk/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
