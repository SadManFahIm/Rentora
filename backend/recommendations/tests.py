"""Tests for Phase 10 similar-rooms endpoint."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room

User = get_user_model()


class SimilarRoomsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="sim_owner", email="sim_owner@example.com", password="test12345"
        )
        # The twin belongs to a *different* landlord — similar-rooms excludes
        # the source owner's own listings (those are just their other rooms).
        self.other_owner = User.objects.create_user(
            username="sim_other", email="sim_other@example.com", password="test12345"
        )
        self.source = Room.objects.create(
            owner=self.owner,
            title="Source Room",
            description="A cozy studio.",
            room_type="studio",
            price=12000,
            area="Dhanmondi",
            address="x",
            lat=23.75,
            lng=90.38,
            amenities=["wifi", "furnished", "ac"],
            size_sqft=350,
        )
        self.twin = Room.objects.create(
            owner=self.other_owner,
            title="Twin Studio",
            description="Similar studio.",
            room_type="studio",
            price=12500,
            area="Dhanmondi",
            address="y",
            lat=23.76,
            lng=90.39,
            amenities=["wifi", "furnished", "ac"],
            size_sqft=360,
        )
        # Deliberately different: other area, type and price.
        Room.objects.create(
            owner=self.owner,
            title="Far Different",
            description="A bed in a dorm.",
            room_type="dorm",
            price=3000,
            area="Mirpur",
            address="z",
            lat=23.8,
            lng=90.4,
            amenities=[],
            size_sqft=100,
        )

    def test_returns_similar_first(self):
        res = self.client.get(f"/api/v1/recommendations/similar/{self.source.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        first = res.data[0]
        self.assertEqual(first["room"]["id"], self.twin.pk)
        self.assertGreaterEqual(first["match_score"], 70)

    def test_unknown_room_is_404(self):
        res = self.client.get("/api/v1/recommendations/similar/99999/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_no_auth_required(self):
        res = self.client.get(f"/api/v1/recommendations/similar/{self.source.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
