"""Phase 15 (C5) — AI Review Summarization tests.

Covers the pure summarizer (sentiment distribution from ratings, bilingual
topic extraction from comments, Bengali summary text, low-review-count
honesty) and the endpoint integration on the existing reviews summary action.
"""

from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking, Review
from bookings.review_summary import _mentioned_topics, analyze_reviews
from rooms.models import Room

User = get_user_model()


def _make_room(owner, title="Summary Room"):
    return Room.objects.create(
        owner=owner,
        title=title,
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


class TopicExtractionTests(APITestCase):
    def test_bangla_topic_keywords(self):
        topics = _mentioned_topics("বাসা খুব পরিষ্কার, বাড়িওয়ালা ভালো, ভাড়া একটু বেশি")
        self.assertIn("cleanliness", topics)
        self.assertIn("landlord", topics)
        self.assertIn("price", topics)

    def test_english_topic_keywords(self):
        topics = _mentioned_topics("Great location, near bus stand, very safe area")
        self.assertIn("location", topics)
        self.assertIn("transport", topics)
        self.assertIn("security", topics)


class AnalyzeReviewsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="sum_owner", email="sum_owner@example.com", password="test12345"
        )
        self.room = _make_room(self.owner)
        self.users = []
        for i in range(4):
            user = User.objects.create_user(
                username=f"sum_user_{i}", email=f"sum_user_{i}@example.com", password="test12345"
            )
            Booking.objects.create(
                room=self.room,
                tenant=user,
                status=Booking.Status.APPROVED,
                check_in=date(2026, 1, 1),
                monthly_rent=9000,
            )
            self.users.append(user)

    def _review(self, user, rating, comment):
        return Review.objects.create(room=self.room, user=user, rating=rating, comment=comment)

    def test_sentiment_from_ratings(self):
        self._review(self.users[0], 5, "great place")
        self._review(self.users[1], 5, "nice")
        self._review(self.users[2], 1, "terrible")
        self._review(self.users[3], 5, "great")
        summary = analyze_reviews(Review.objects.filter(room=self.room))
        self.assertEqual(summary["review_count"], 4)
        self.assertEqual(summary["sentiment"]["positive_pct"], 75)
        self.assertEqual(summary["sentiment"]["negative_pct"], 25)
        self.assertEqual(summary["sentiment"]["neutral_pct"], 0)
        self.assertEqual(summary["sentiment"]["overall"], "positive")

    def test_topics_from_comments(self):
        self._review(self.users[0], 5, "very clean and tidy, great value")
        self._review(self.users[1], 4, "clean, helpful landlord")
        self._review(self.users[2], 3, "location is convenient")
        self._review(self.users[3], 4, "safe and quiet")
        summary = analyze_reviews(Review.objects.filter(room=self.room))
        topic_keys = [t["topic"] for t in summary["topics"]]
        self.assertIn("cleanliness", topic_keys)
        self.assertTrue(all(t["label_bn"] for t in summary["topics"]))

    def test_summary_is_bangla_and_grounded(self):
        self._review(self.users[0], 5, "great place")
        self._review(self.users[1], 4, "nice and clean")
        self._review(self.users[2], 1, "terrible")
        self._review(self.users[3], 3, "okay")
        summary = analyze_reviews(Review.objects.filter(room=self.room))
        self.assertIn("৪", summary["summary_bn"])  # Bengali digit for 4 reviews
        self.assertIn("৫০", summary["summary_bn"])  # 50% positive
        self.assertIn("২৫", summary["summary_bn"])  # 25% negative
        self.assertIn("note", summary)
        self.assertIn("Automatic", summary["note"])

    def test_few_reviews_flag_reliability(self):
        self._review(self.users[0], 5, "great")
        summary = analyze_reviews(Review.objects.filter(room=self.room))
        self.assertIn("নির্ভরযোগ্য নয়", summary["summary_bn"])
        self.assertNotIn("ইতিবাচক", summary["summary_bn"])

    def test_no_reviews(self):
        summary = analyze_reviews(Review.objects.filter(room=self.room))
        self.assertEqual(summary["review_count"], 0)
        self.assertEqual(summary["sentiment"]["overall"], "none")
        self.assertIn("কোনো রিভিউ", summary["summary_bn"])


class SummaryEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="end_owner", email="end_owner@example.com", password="test12345"
        )
        self.room = _make_room(self.owner)

    def test_summary_includes_ai_summary(self):
        users = []
        for i in range(3):
            user = User.objects.create_user(
                username=f"end_user_{i}", email=f"end_user_{i}@example.com", password="test12345"
            )
            Booking.objects.create(
                room=self.room,
                tenant=user,
                status=Booking.Status.APPROVED,
                check_in=date(2026, 2, 1),
                monthly_rent=9000,
            )
            Review.objects.create(room=self.room, user=user, rating=4 + i % 2, comment="clean")
            users.append(user)
        response = self.client.get(f"/api/v1/reviews/summary/?room={self.room.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_reviews"], 3)
        ai = response.data["ai_summary"]
        self.assertEqual(ai["review_count"], 3)
        self.assertTrue(ai["summary_bn"])
        self.assertIn("cleanliness", [t["topic"] for t in ai["topics"]])
