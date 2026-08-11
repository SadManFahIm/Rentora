"""Tests for the shared-wishlist public view (Phase 10)."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room
from wishlist.models import Wishlist

User = get_user_model()


class SharedWishlistTests(APITestCase):
    def setUp(self):
        self.sharer = User.objects.create_user(
            username="sharer", email="sharer@example.com", password="test12345"
        )
        self.other_owner = User.objects.create_user(
            username="ow", email="ow@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.other_owner,
            title="Shared Room",
            description="d",
            room_type="single",
            price=9000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            amenities=["wifi"],
            size_sqft=200,
        )
        Wishlist.objects.create(user=self.sharer, room=self.room)

    def test_public_share_link_lists_rooms(self):
        res = self.client.get(f"/api/v1/wishlist/share/{self.sharer.wishlist_share_token}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["owner"], "sharer")
        self.assertEqual(len(res.data["rooms"]), 1)
        self.assertEqual(res.data["rooms"][0]["title"], "Shared Room")

    def test_bad_token_is_404(self):
        res = self.client.get("/api/v1/wishlist/share/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
