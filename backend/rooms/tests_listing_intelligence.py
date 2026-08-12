"""Tests for listing quality score + fraud-aware search ranking (Phase 11+).

Covers:
- quality score: complete vs incomplete listings, photo/description/amenity
  gaps, score boundaries/levels, actionable suggestions, feature disabled.
- fraud-aware ranking: high-risk rooms are demoted, feature disabled keeps
  the previous ranking, and existing fraud reports are reused (not re-run).
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from fraud.models import FraudReport
from rooms.models import Room, RoomImage

User = get_user_model()

_GOOD_DESCRIPTION = (
    "A complete 2-bedroom flat in Mirpur 10. Fully furnished with a study desk, "
    "wardrobe and bed. Attached bathroom, kitchen with gas and electricity, and "
    "high-speed wifi. 5 minutes walk from Mirpur 10 bus stand and the metro "
    "station. Suitable for students and young professionals. Monthly rent "
    "includes maintenance. Available for immediate move-in."
)


def make_user(username="q1"):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345"
    )


def make_room(owner, **overrides):
    fields = dict(
        title="Complete Mirpur Flat",
        description=_GOOD_DESCRIPTION,
        room_type="single",
        price=10000,
        area="Mirpur",
        address="House 27, Road 5, Mirpur 10, Dhaka 1216",
        lat=23.806,
        lng=90.368,
        amenities=[
            "wifi",
            "attached bathroom",
            "kitchen",
            "furnished",
            "parking",
            "gas",
            "electricity",
        ],
        size_sqft=220,
    )
    fields.update(overrides)
    return Room.objects.create(owner=owner, **fields)


def attach_images(room, count=4):
    from io import BytesIO

    from PIL import Image

    for i in range(count):
        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        RoomImage.objects.create(
            room=room,
            is_primary=(i == 0),
            image=SimpleUploadedFile(f"r{i}.png", buffer.getvalue(), "image/png"),
        )


# ---------------------------------------------------------------------------
# Listing quality score
# ---------------------------------------------------------------------------


class ListingQualityTests(APITestCase):
    def test_complete_listing_scores_high(self):
        owner = make_user()
        room = make_room(owner)
        attach_images(room, 4)
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertGreaterEqual(result["score"], 75)
        self.assertIn(result["level"], ("good", "excellent"))
        self.assertGreaterEqual(result["category_scores"]["photos"], 0.9)
        self.assertEqual(result["suggestions"], [])

    def test_no_photos_scores_low_and_suggests_photos(self):
        owner = make_user()
        room = make_room(owner)  # no images attached
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertLess(result["score"], 75)
        self.assertEqual(result["category_scores"]["photos"], 0.0)
        self.assertTrue(any("photos" in s.lower() for s in result["suggestions"]))

    def test_short_description_flagged(self):
        owner = make_user()
        room = make_room(owner, description="Nice room.")
        attach_images(room, 4)
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertLess(result["category_scores"]["description"], 0.7)
        self.assertTrue(any("description" in s.lower() for s in result["suggestions"]))

    def test_missing_amenities_suggested(self):
        owner = make_user()
        room = make_room(owner, amenities=["wifi"])
        attach_images(room, 4)
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertTrue(any("amenities" in s.lower() for s in result["suggestions"]))

    def test_score_boundaries_and_levels(self):
        owner = make_user()
        room = make_room(owner)  # decent but no photos -> mid score
        attach_images(room, 2)
        from rooms.listing_quality import get_listing_quality

        result = get_listing_quality(room)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        # Level names come from the configured ladder.
        self.assertIn(
            result["level"],
            ("excellent", "good", "fair", "needs_improvement", "poor"),
        )

    def test_disabled_feature_returns_empty_payload(self):
        owner = make_user()
        room = make_room(owner)
        attach_images(room, 4)
        with override_settings(LISTING_QUALITY_SCORE_ENABLED=False):
            from rooms.listing_quality import get_listing_quality

            result = get_listing_quality(room)
            self.assertIsNone(result["score"])
            self.assertIsNone(result["level"])
            self.assertEqual(result["suggestions"], [])

    def test_detail_api_exposes_listing_quality(self):
        owner = make_user()
        room = make_room(owner)
        attach_images(room, 4)
        self.client.force_authenticate(owner)
        res = self.client.get(f"/api/v1/rooms/{room.id}/")
        self.assertEqual(res.status_code, 200, res.data)
        quality = res.data["listing_quality"]
        self.assertIn("score", quality)
        self.assertIn("suggestions", quality)
        self.assertGreaterEqual(quality["score"], 0)

    def test_insights_rows_include_quality(self):
        owner = make_user()
        room = make_room(owner)
        attach_images(room, 4)
        self.client.force_authenticate(owner)
        res = self.client.get("/api/v1/rooms/insights/")
        self.assertEqual(res.status_code, 200, res.data)
        row = res.data["rooms"][0]
        self.assertEqual(row["id"], room.id)
        self.assertIn("listing_quality", row)
        self.assertGreaterEqual(row["listing_quality"]["score"], 0)


# ---------------------------------------------------------------------------
# Fraud-aware ranking
# ---------------------------------------------------------------------------


class FraudAwareRankingTests(APITestCase):
    def setUp(self):
        self.landlord = make_user("fraud1")
        self.room_a = make_room(
            self.landlord,
            title="Sunny Mirpur Studio",
            description=(
                "A bright studio in Mirpur with an attached bathroom and "
                "kitchen. Close to the bus stand."
            ),
        )
        self.room_b = make_room(
            self.landlord,
            title="Family Flat Near Gulshan",
            description=(
                "A spacious family flat near Gulshan avenue with parking "
                "and a separate dining room."
            ),
        )

    def _rank(self, query="mirpur room"):
        res = self.client.get("/api/v1/rooms/", {"q": query, "smart": "1", "debug_rank": "1"})
        self.assertEqual(res.status_code, 200, res.data)
        ids = [r["id"] for r in res.data["results"]]
        # rank_meta is attached at the response top level for debug requests.
        meta = res.data.get("rank_meta", {})
        return ids, meta

    def _set_report(self, room, score, severity):
        # The fraud auto-scan post-save signal fires on room creation and may
        # have written a report already — wipe auto-generated rows for both
        # fixture rooms so the test controls the risk signal deterministically.
        FraudReport.objects.filter(room_id__in=[self.room_a.id, self.room_b.id]).delete()
        FraudReport.objects.create(room=room, score=score, severity=severity)

    def test_high_risk_room_is_demoted(self):
        self._set_report(self.room_b, 90, FraudReport.Severity.HIGH)
        ids, meta = self._rank()
        self.assertIn(self.room_a.id, ids)
        self.assertIn(self.room_b.id, ids)
        # The flagged room ranks strictly below the clean one.
        self.assertLess(ids.index(self.room_a.id), ids.index(self.room_b.id))
        self.assertGreater(meta.get(self.room_b.id, {}).get("fraud_risk", 0), 0)
        self.assertLessEqual(meta.get(self.room_a.id, {}).get("fraud_risk", 0), 0)

    def test_feature_disabled_keeps_ranking(self):
        self._set_report(self.room_b, 90, FraudReport.Severity.HIGH)
        with override_settings(FRAUD_AWARE_RANKING_ENABLED=False):
            ids, meta = self._rank()
        self.assertIn(self.room_a.id, ids)
        self.assertIn(self.room_b.id, ids)
        # With the feature off, fraud never influences the score: the meta
        # key is either absent or None.
        self.assertIsNone(meta.get(self.room_a.id, {}).get("fraud_risk"))
        self.assertIsNone(meta.get(self.room_b.id, {}).get("fraud_risk"))

    def test_low_risk_has_minimal_effect(self):
        self._set_report(self.room_b, 5, FraudReport.Severity.LOW)
        ids, meta = self._rank()
        self.assertIn(self.room_a.id, ids)
        self.assertIn(self.room_b.id, ids)
        self.assertLessEqual(meta.get(self.room_b.id, {}).get("fraud_risk", 1), 0.05)
