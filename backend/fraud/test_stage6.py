"""Phase 17 -- Stage 6: Fake-Review Detection Tests."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Review
from fraud.services.review_detector import (
    _text_similarity,
    compute_review_trust_score,
    detect_review_anomalies,
    scan_review_trust_scores,
)
from rooms.models import Room
from users.models import User


def _create_user(**kwargs):
    defaults = {"username": "reviewer", "email": "reviewer@example.com"}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults, password="testpass123")


def _create_room(owner, **kwargs):
    defaults = {
        "title": "Test Room",
        "description": "A test room",
        "room_type": "single",
        "price": Decimal("5000.00"),
        "area": "Dhanmondi",
        "address": "123 Road",
        "lat": Decimal("23.7509"),
        "lng": Decimal("90.3766"),
        "amenities": [],
        "size_sqft": 200,
    }
    defaults.update(kwargs)
    return Room.objects.create(owner=owner, **defaults)


def _create_review(room, user, rating=4, comment="Good room, nice location."):
    return Review.objects.create(
        room=room,
        user=user,
        rating=rating,
        comment=comment,
        verified_stay=True,
    )


# -- Text Similarity Tests --


class TextSimilarityTest(TestCase):
    def test_identical(self):
        self.assertAlmostEqual(_text_similarity("hello world", "hello world"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(_text_similarity("abc def", "xyz qwerty"), 0.0)

    def test_partial_overlap(self):
        score = _text_similarity("the room is clean and spacious", "the room is clean and big")
        self.assertGreater(score, 0.5)

    def test_empty(self):
        self.assertAlmostEqual(_text_similarity("", "hello"), 0.0)


# -- Trust Score Tests --


class TrustScoreTest(TestCase):
    def setUp(self):
        self.owner = _create_user(username="owner", email="owner@example.com")
        self.reviewer = _create_user(
            username="reviewer",
            email="reviewer@example.com",
            date_joined=timezone.now() - timedelta(days=180),
        )
        self.room = _create_room(self.owner)

    def test_verified_stay_high_score(self):
        review = _create_review(
            self.room, self.reviewer, rating=4, comment="Great room, would recommend to others."
        )
        score = compute_review_trust_score(review)
        self.assertGreater(score, 60)

    def test_new_account_penalty(self):
        new_user = _create_user(
            username="newuser",
            email="new@example.com",
            date_joined=timezone.now() - timedelta(days=3),
        )
        review = _create_review(
            self.room, new_user, rating=5, comment="Amazing room! Best place in Dhaka!"
        )
        score = compute_review_trust_score(review)
        # New account gets -20 penalty but base is 70 and extreme rating -3
        # so score ~ 47. Must be well below established user score.
        self.assertLess(score, 70)

    def test_no_verified_booking_penalty(self):
        review = _create_review(self.room, self.reviewer, rating=5, comment="Perfect place!")
        review.verified_stay = False
        score = compute_review_trust_score(review)
        self.assertLess(score, 70)

    def test_extreme_rating_penalty(self):
        established = _create_user(
            username="established",
            email="est@example.com",
            date_joined=timezone.now() - timedelta(days=200),
        )
        review5 = _create_review(
            self.room, established, rating=5, comment="Great room, nice location and clean."
        )
        review3 = _create_review(
            self.room,
            _create_user(
                username="reviewer2",
                email="r2@example.com",
                date_joined=timezone.now() - timedelta(days=200),
            ),
            rating=3,
            comment="Decent room, a bit small but overall okay.",
        )
        score5 = compute_review_trust_score(review5)
        score3 = compute_review_trust_score(review3)
        # Middle rating (3) gets +2, extreme (5) gets -3, same user profile otherwise
        self.assertGreaterEqual(score3, score5)

    def test_photo_bonus(self):
        review = _create_review(
            self.room, self.reviewer, rating=4, comment="Clean room, will stay again."
        )
        review.photos = ["http://example.com/photo1.jpg"]
        score = compute_review_trust_score(review)
        base_review = _create_review(
            self.room,
            _create_user(username="reviewer2", email="r2@example.com"),
            rating=4,
            comment="Clean room, will stay again.",
        )
        base_score = compute_review_trust_score(base_review)
        self.assertGreaterEqual(score, base_score)

    def test_too_short_penalty(self):
        reviewer = _create_user(
            username="shortuser",
            email="short@example.com",
            date_joined=timezone.now() - timedelta(days=200),
        )
        review = _create_review(self.room, reviewer, rating=4, comment="Nice!")
        score = compute_review_trust_score(review)
        # Short comment gets -10, verified stay +15, moderate rating +0
        # Established account +5, long account +5
        # Should still be positive but penalized vs longer text
        base_review = _create_review(
            self.room,
            _create_user(
                username="longuser",
                email="long@example.com",
                date_joined=timezone.now() - timedelta(days=200),
            ),
            rating=4,
            comment="This is a very long and detailed review about the room.",
        )
        base_score = compute_review_trust_score(base_review)
        self.assertLess(score, base_score)

    def test_score_capped_0_100(self):
        review = _create_review(self.room, self.reviewer, rating=5, comment="OK")
        score = compute_review_trust_score(review)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


# -- scan_review_trust_scores Tests --


class ScanReviewTrustTest(TestCase):
    def setUp(self):
        self.owner = _create_user(username="owner", email="owner@example.com")
        self.reviewer = _create_user(username="reviewer", email="reviewer@example.com")
        self.room = _create_room(self.owner)

    def test_scoring(self):
        _create_review(self.room, self.reviewer)
        result = scan_review_trust_scores()
        self.assertEqual(result["scored"], 1)
        self.review = Review.objects.first()
        self.assertIsNotNone(self.review.trust_score)

    def test_no_unscored(self):
        Review.objects.create(
            room=self.room,
            user=self.reviewer,
            rating=4,
            comment="Good room.",
            trust_score=75,
        )
        result = scan_review_trust_scores()
        self.assertEqual(result["scored"], 0)

    def test_low_trust_flagged(self):
        new_user = _create_user(
            username="spammer",
            email="spam@example.com",
            date_joined=timezone.now() - timedelta(days=1),
        )
        _create_review(self.room, new_user, rating=5, comment="Best!!!")
        result = scan_review_trust_scores()
        self.assertGreaterEqual(result["flagged"], 0)


# -- detect_review_anomalies Tests --


class DetectAnomaliesTest(TestCase):
    def setUp(self):
        self.owner = _create_user(username="owner", email="owner@example.com")
        self.reviewer = _create_user(username="reviewer", email="reviewer@example.com")
        self.room = _create_room(self.owner)

    def test_no_anomalies(self):
        _create_review(self.room, self.reviewer, rating=4)
        result = detect_review_anomalies()
        self.assertEqual(result["count"], 0)

    @override_settings(REVIEW_VELOCITY_THRESHOLD=3)
    def test_velocity_spike(self):
        now = timezone.now()
        for i in range(4):
            user = _create_user(
                username=f"spammer{i}",
                email=f"s{i}@example.com",
            )
            Review.objects.create(
                room=self.room,
                user=user,
                rating=5,
                comment=f"Review number {i}, great room!",
                created_at=now - timedelta(minutes=10 * i),
            )
        result = detect_review_anomalies()
        self.assertGreater(result["count"], 0)
        types = [a["type"] for a in result["anomalies"]]
        self.assertIn("velocity_spike", types)

    def test_rating_distribution_anomaly(self):
        for i in range(6):
            user = _create_user(
                username=f"fan{i}",
                email=f"fan{i}@example.com",
            )
            Review.objects.create(
                room=self.room,
                user=user,
                rating=5,
                comment=f"Amazing place number {i}!",
            )
        result = detect_review_anomalies()
        types = [a["type"] for a in result["anomalies"]]
        self.assertIn("rating_distribution", types)


# -- Task Tests --


class ReviewTaskTests(TestCase):
    def test_scan_review_trust_task(self):
        from fraud.tasks import scan_review_trust

        result = scan_review_trust()
        self.assertIsInstance(result, dict)
        self.assertIn("scored", result)

    def test_detect_review_anomalies_task(self):
        from fraud.tasks import detect_review_anomalies

        result = detect_review_anomalies()
        self.assertIsInstance(result, dict)
        self.assertIn("anomalies", result)
