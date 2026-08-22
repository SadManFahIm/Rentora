"""Fake-Review Detection service (Phase 17, Stage 6).

Two complementary detectors:

1. **Review Trust Scoring** (``compute_review_trust_score``):
   Scores individual reviews 0-100 based on reviewer behaviour signals:
   - Reviewer's account age and booking history
   - Review timing relative to booking
   - Text similarity to other reviews by same author
   - Rating extremity (1-star and 5-star are slightly less trusted)
   - Photo evidence presence

2. **Review Anomaly Detection** (``detect_review_anomalies``):
   Room-level aggregation that flags:
   - Rating distribution anomalies (e.g. sudden influx of 5-star)
   - Velocity spikes (many reviews in short window)
   - Cross-room patterns (same reviewer, many rooms, all 5-star)
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)

# -- Trust Scoring Weights --

ACCOUNT_AGE_DAYS_FULL_TRUST = 90  # accounts older than this get full trust
MIN_BOOKINGS_FOR_TRUST = 1  # at least 1 completed booking
VELOCITY_THRESHOLD = 4  # reviews per hour from same user = suspicious
SIMILARITY_THRESHOLD = 0.8  # text similarity threshold for duplicates


def compute_review_trust_score(review) -> int:
    """Compute a trust score (0-100) for a single review.

    Higher = more trustworthy. Uses only deterministic signals — no ML.
    The score is explainable via the ``signals`` list in the detail dict.
    """
    from bookings.models import Booking

    score = 70  # base score
    signals = []

    user = review.user
    room = review.room

    # 1. Account age — newer accounts are slightly less trusted
    account_age_days = (timezone.now() - user.date_joined).days
    if account_age_days < 7:
        score -= 20
        signals.append("new_account_7d")
    elif account_age_days < 30:
        score -= 10
        signals.append("new_account_30d")
    elif account_age_days >= ACCOUNT_AGE_DAYS_FULL_TRUST:
        score += 5
        signals.append("established_account")

    # 2. Verified booking — the most important trust signal
    has_booking = Booking.objects.filter(
        tenant=user,
        room=room,
        status="completed",
    ).exists()
    if review.verified_stay:
        score += 15
        signals.append("verified_stay")
    elif has_booking:
        score += 10
        signals.append("has_completed_booking")
    else:
        score -= 15
        signals.append("no_verified_booking")

    # 3. Review timing — reviews posted within 7 days of checkout are most
    #    trustworthy; very late reviews (>60 days) are slightly suspect
    if has_booking:
        booking = (
            Booking.objects.filter(tenant=user, room=room, status="completed")
            .order_by("-check_out")
            .first()
        )
        if booking and booking.check_out:
            days_since = (timezone.now() - booking.check_out).days
            if days_since <= 7:
                score += 5
                signals.append("timely_review")
            elif days_since > 60:
                score -= 5
                signals.append("late_review")

    # 4. Rating extremity — 1-star and 5-star are slightly less trusted
    #    than 2-4 star reviews (extreme ratings are easier to fake/generate)
    if review.rating in (1, 5):
        score -= 3
        signals.append("extreme_rating")
    elif review.rating in (2, 4):
        signals.append("moderate_rating")
    else:
        score += 2
        signals.append("middle_rating")

    # 5. Photo evidence — reviews with photos are more trustworthy
    if review.photos:
        score += 5
        signals.append("has_photos")

    # 6. Review text quality
    comment = (review.comment or "").strip()
    if len(comment) < 10:
        score -= 10
        signals.append("too_short")
    elif len(comment) > 100:
        score += 3
        signals.append("substantive_text")

    # 7. Reviewer volume — users who review many rooms are slightly suspect
    #    unless they have many completed bookings
    reviewer_review_count = type(review).objects.filter(user=user).count()
    reviewer_booking_count = Booking.objects.filter(tenant=user, status="completed").count()
    if reviewer_review_count > 5 and reviewer_booking_count < reviewer_review_count:
        score -= 10
        signals.append("high_review_to_booking_ratio")

    # 8. Duplicate text detection — check if this review is very similar
    #    to other reviews by the same author
    if len(comment) >= 20:
        other_reviews = (
            type(review)
            .objects.filter(user=user)
            .exclude(pk=review.pk)
            .values_list("comment", flat=True)[:50]
        )
        for other_comment in other_reviews:
            if _text_similarity(comment, other_comment) >= SIMILARITY_THRESHOLD:
                score -= 15
                signals.append("duplicate_text_detected")
                break

    return max(0, min(100, score))


def _text_similarity(a: str, b: str) -> float:
    """Simple word-overlap Jaccard similarity. Deterministic, no ML."""
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def scan_review_trust_scores() -> dict:
    """Score all un-scored reviews. Called daily by the beat task.

    Returns summary stats.
    """
    from bookings.models import Review

    unscored = Review.objects.filter(trust_score__isnull=True)
    scored = 0
    flagged = 0

    for review in unscored.select_related("user", "room").iterator():
        trust_score = compute_review_trust_score(review)
        review.trust_score = trust_score
        review.save(update_fields=["trust_score"])
        scored += 1

        # Flag low-trust reviews for moderation
        if trust_score < 30:
            _flag_review(review, trust_score, "low_trust_score")
            flagged += 1

    return {"scored": scored, "flagged": flagged}


def _flag_review(review, trust_score: int, reason: str):
    """Create a FraudSignal for a suspicious review."""
    from fraud.models import FraudReport, FraudSignal

    detector = (
        FraudSignal.Detector.REVIEW_FAKE if trust_score < 20 else FraudSignal.Detector.REVIEW_SPAM
    )

    # Get or create FraudReport for the room
    report, _ = FraudReport.objects.get_or_create(
        room=review.room,
        defaults={"severity": "low"},
    )

    FraudSignal.objects.create(
        report=report,
        detector=detector,
        severity="low" if trust_score >= 20 else "medium",
        message=(f"Review #{review.pk} scored {trust_score}/100 trust (reason: {reason})."),
        detail={
            "review_id": review.pk,
            "reviewer": review.user.username,
            "trust_score": trust_score,
            "reason": reason,
            "rating": review.rating,
        },
    )


def detect_review_anomalies() -> dict:
    """Detect room-level review anomalies: velocity spikes and rating
    distribution shifts. Called daily by the beat task.

    Returns summary of anomalies found.
    """
    from bookings.models import Review

    anomalies = []
    now = timezone.now()

    # 1. Velocity spike detection: rooms with > N reviews in last 24h
    velocity_threshold = getattr(settings, "REVIEW_VELOCITY_THRESHOLD", 5)
    recent_cutoff = now - timedelta(hours=24)

    rooms_with_velocity = (
        Review.objects.filter(created_at__gte=recent_cutoff)
        .values("room_id")
        .annotate(count=Count("id"))
        .filter(count__gte=velocity_threshold)
    )

    for row in rooms_with_velocity:
        anomalies.append(
            {
                "type": "velocity_spike",
                "room_id": row["room_id"],
                "review_count": row["count"],
                "period": "24h",
            }
        )

    # 2. Rating distribution anomaly: rooms where >80% of reviews are
    #    5-star AND total reviews >= 5 (possible bought reviews)
    rooms_with_many_reviews = (
        Review.objects.values("room_id").annotate(total=Count("id")).filter(total__gte=5)
    )

    for row in rooms_with_many_reviews:
        room_id = row["room_id"]
        total = row["total"]
        five_star = Review.objects.filter(room_id=room_id, rating=5).count()
        if five_star / total > 0.8 and total >= 5:
            anomalies.append(
                {
                    "type": "rating_distribution",
                    "room_id": room_id,
                    "five_star_pct": round(five_star / total * 100, 1),
                    "total_reviews": total,
                }
            )

    # 3. Cross-room same-reviewer anomaly: users who reviewed >= 3 rooms
    #    with all 5-star ratings (potential fake reviewer ring)
    suspicious_reviewers = (
        Review.objects.filter(rating=5)
        .values("user_id")
        .annotate(
            room_count=Count("room_id", distinct=True),
            review_count=Count("id"),
        )
        .filter(room_count__gte=3, review_count__gte=3)
    )

    for row in suspicious_reviewers:
        # Verify ALL reviews by this user are 5-star
        user_reviews = Review.objects.filter(user_id=row["user_id"])
        all_five = user_reviews.exclude(rating=5).count() == 0
        if all_five:
            anomalies.append(
                {
                    "type": "cross_room_suspect",
                    "user_id": row["user_id"],
                    "room_count": row["room_count"],
                    "review_count": row["review_count"],
                }
            )

    return {"anomalies": anomalies, "count": len(anomalies)}
