"""Tests for Phase 10 review upgrades — landlord reply, summary, photos."""

from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking, Review
from rooms.models import Room

User = get_user_model()


class ReviewsV2Tests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="rl", email="rl@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="rt", email="rt@example.com", password="test12345"
        )
        self.other = User.objects.create_user(
            username="rx", email="rx@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Review Room",
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
        Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 1),
            monthly_rent=9000,
        )
        Review.objects.create(room=self.room, user=self.tenant, rating=5, comment="Great stay")
        Review.objects.create(
            room=self.room, user=self.other, rating=3, comment="Okay", verified_stay=True
        )

    def test_landlord_can_reply(self):
        self.client.force_authenticate(self.landlord)
        review_id = Review.objects.get(user=self.tenant).pk
        res = self.client.post(
            f"/api/v1/reviews/{review_id}/reply/",
            {"reply": "Thank you for staying!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        review = Review.objects.get(pk=review_id)
        self.assertEqual(review.reply, "Thank you for staying!")
        self.assertIsNotNone(review.replied_at)

    def test_non_owner_cannot_reply(self):
        self.client.force_authenticate(self.other)
        review_id = Review.objects.get(user=self.tenant).pk
        res = self.client.post(
            f"/api/v1/reviews/{review_id}/reply/",
            {"reply": "hacked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_summary_returns_rating_breakdown(self):
        res = self.client.get(f"/api/v1/reviews/summary/?room={self.room.pk}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_reviews"], 2)
        self.assertEqual(res.data["average_rating"], 4.0)
        self.assertEqual(res.data["counts_per_star"]["5"], 1)
        self.assertEqual(res.data["counts_per_star"]["3"], 1)
        self.assertEqual(len(res.data["recent"]), 2)

    def test_create_review_with_photos(self):
        tenant2 = User.objects.create_user(
            username="rt2", email="rt2@example.com", password="test12345"
        )
        Booking.objects.create(
            room=self.room,
            tenant=tenant2,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 2, 1),
            monthly_rent=9000,
        )
        self.client.force_authenticate(tenant2)
        res = self.client.post(
            "/api/v1/reviews/",
            {
                "room": self.room.pk,
                "rating": 4,
                "comment": "Updated",
                "photos": ["/media/reviews/pic1.jpg", "/media/reviews/pic2.jpg"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(len(res.data["photos"]), 2)
