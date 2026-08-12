"""Phase 11+ AI search tests — neural hybrid ranking, typo tolerance, area
aliases, personalized re-ranking, price-anomaly badge, and graceful fallback.

Covers the search-and-discovery upgrade:
- **Semantic (cross-language)** — \"affordable student room\" surfaces a room
  whose description is entirely Bangla, in both query directions.
- **Typo tolerance** — \"mirpore\" / \"মিরপূর\" still find Mirpur listings.
- **Area aliases** — Dhanmondi/Dhanmondhi/ধানমন্ডি/ধানমন্ডি ২৭ all resolve.
- **Personalization** — logged-in users get preference-aware ordering, cold
  start falls back safely, and hard filters (budget/area) always win.
- **Price anomaly** — the badge renders only above the threshold and only
  with a confident prediction; disabling the flag removes the field.
- **Fallback** — every signal is disable-able; search never 500s.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from recommendations.models import UserActivity
from rooms.area_aliases import find_areas_in_text, resolve_area
from rooms.models import Room
from rooms.price_anomaly import get_price_anomaly

User = get_user_model()


def make_room(
    owner,
    title,
    area="Mirpur",
    price=9000,
    room_type="single",
    description="A cozy room near the university.",
    gender="any",
    **extra,
):
    return Room.objects.create(
        owner=owner,
        title=title,
        description=description,
        room_type=room_type,
        price=price,
        area=area,
        address="12 Road",
        lat=23.8,
        lng=90.4,
        amenities=["wifi", "furnished"],
        size_sqft=250,
        gender_preference=gender,
        **extra,
    )


class AreaAliasTests(APITestCase):
    def test_canonical_aliases_resolve(self):
        for query, expected in [
            ("dhanmondi", "Dhanmondi"),
            ("Dhanmondhi", "Dhanmondi"),
            ("ধানমন্ডি", "Dhanmondi"),
            ("ধানমণ্ডি", "Dhanmondi"),
            ("ধানমন্ডি ২৭", "Dhanmondi"),
            ("mirpur", "Mirpur"),
            ("mirpur 10", "Mirpur"),
            ("মিরপুর", "Mirpur"),
            ("uttara sector 10", "Uttara"),
            ("gulshan circle 2", "Gulshan"),
        ]:
            self.assertEqual(resolve_area(query), expected, f"{query!r} -> {expected}")

    def test_fuzzy_same_script_typos(self):
        # Same-script typos resolve via the bounded gazetteer.
        self.assertEqual(resolve_area("mirpore"), "Mirpur")
        self.assertEqual(resolve_area("মিরপূর"), "Mirpur")
        self.assertEqual(resolve_area("uttra"), "Uttara")

    def test_find_areas_in_text_whole_phrase(self):
        self.assertEqual(find_areas_in_text("দশ হাজার এর মধ্যে মিরপূর", fuzzy=True), ["Mirpur"])
        self.assertEqual(
            find_areas_in_text("room in Dhanmondhi near uttra", fuzzy=True),
            ["Dhanmondi", "Uttara"],
        )


class SemanticCrossLanguageTests(APITestCase):
    """The spec's headline case: English query finds the Bangla listing."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ai1", email="ai1@example.com", password="test12345"
        )
        # Deliberately *not* in English: the semantic leg must carry meaning
        # across scripts ("কম বাজেটের শিক্ষার্থীদের থাকার রুম").
        self.bangla_room = make_room(
            self.landlord,
            "Budget room for students",
            area="Mirpur",
            price=6000,
            description="কম বাজেটের শিক্ষার্থীদের থাকার রুম, একটি আরামদায়ক ঘর",
        )
        self.unrelated = make_room(
            self.landlord,
            "Luxury penthouse",
            area="Gulshan",
            price=40000,
            room_type="studio",
            description="Premium ocean view apartment with swimming pool and gym.",
        )

    def test_english_query_surfaces_bangla_listing(self):
        res = self.client.get("/api/v1/rooms/?q=affordable student room&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(self.bangla_room.id, ids)
        # The semantically relevant listing ranks above the unrelated one.
        self.assertLess(ids.index(self.bangla_room.id), ids.index(self.unrelated.id))

    def test_bangla_query_surfaces_bangla_listing_first(self):
        # No area mention ("Uttara" in the earlier draft was filtered to
        # zero — correctly — because the fixture room is in Mirpur):
        # pure-concept Bangla query, cross-script discovery.
        res = self.client.get("/api/v1/rooms/?q=কম দামের শিক্ষার্থীদের রুম&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(self.bangla_room.id, ids)
        self.assertLess(ids.index(self.bangla_room.id), ids.index(self.unrelated.id))


class TypoToleranceApiTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="typo", email="typo@example.com", password="test12345"
        )
        self.mirpur_room = make_room(self.landlord, "Mirpur Flat", area="Mirpur")
        self.dhanmondi_room = make_room(self.landlord, "Dhanmondi Flat", area="Dhanmondi")

    def test_english_typo_finds_area(self):
        res = self.client.get("/api/v1/rooms/?q=mirpore&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(self.mirpur_room.id, ids)
        # NL filter applied: only the Mirpur listing qualifies.
        self.assertEqual(res.data["count"], 1)
        self.assertIn("Mirpur", res.data["nl_parsed"]["areas"])

    def test_bangla_typo_finds_area(self):
        res = self.client.get("/api/v1/rooms/?q=মিরপূর&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.mirpur_room.id)
        self.assertIn("Mirpur", res.data["nl_parsed"]["areas"])


class PersonalizationTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="perl", email="perl@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="pert", email="pert@example.com", password="test12345"
        )
        # Two rooms that are near-equal on raw relevance for the query "room".
        self.uttara_room = make_room(self.landlord, "Uttara Family Room", area="Uttara")
        self.dhanmondi_room = make_room(self.landlord, "Dhanmondi Family Room", area="Dhanmondi")

    def test_history_boosts_preferred_area(self):
        # The tenant has a strong history of interest in *Uttara* rooms.
        UserActivity.objects.create(
            user=self.tenant,
            room=self.uttara_room,
            activity_type=UserActivity.ActivityType.WISHLIST,
        )
        self.client.force_authenticate(self.tenant)
        res = self.client.get("/api/v1/rooms/?q=family room&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(self.uttara_room.id, ids)
        self.assertIn(self.dhanmondi_room.id, ids)
        self.assertEqual(ids[0], self.uttara_room.id)

    def test_cold_start_no_crash_and_default_order(self):
        # No history at all — personalization is a no-op, ordering is
        # relevance-based, nothing crashes.
        self.client.force_authenticate(self.tenant)
        res = self.client.get("/api/v1/rooms/?q=family room&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data["results"]]
        self.assertEqual(len(ids), 2)

    def test_hard_filters_always_win_over_personalization(self):
        # Tenant prefers Dhanmondi (viewed it), but the query's budget filter
        # is Uttara-only — the expensive Dhanmondi room must not appear.
        UserActivity.objects.create(
            user=self.tenant,
            room=self.dhanmondi_room,
            activity_type=UserActivity.ActivityType.VIEW,
        )
        self.client.force_authenticate(self.tenant)
        res = self.client.get("/api/v1/rooms/?q=১০ হাজার এর মধ্যে uttara&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.uttara_room.id)


class PriceAnomalyTests(APITestCase):
    def test_badge_above_threshold(self):
        with patch(
            "pricing.services.prediction.predict_price_from_model",
            return_value={"model_confidence": "high", "predicted_price": 10000},
        ):
            room = make_room(self._owner(), "Priced High", area="Dhanmondi", price=12500)
            anomaly = get_price_anomaly(room)
        self.assertIsNotNone(anomaly)
        self.assertEqual(anomaly["difference_percentage"], 25)
        self.assertEqual(anomaly["direction"], "above_market")
        self.assertEqual(anomaly["badge"], "25% above market")

    def test_no_badge_below_threshold(self):
        with patch(
            "pricing.services.prediction.predict_price_from_model",
            return_value={"model_confidence": "high", "predicted_price": 10000},
        ):
            room = make_room(self._owner(), "Close to Market", price=11000)
            self.assertIsNone(get_price_anomaly(room))

    def test_no_badge_low_confidence(self):
        with patch(
            "pricing.services.prediction.predict_price_from_model",
            return_value={"model_confidence": "low", "predicted_price": 10000},
        ):
            room = make_room(self._owner(), "Low Confidence", price=15000)
            self.assertIsNone(get_price_anomaly(room))

    def test_disabled_flag_removes_field(self):
        with override_settings(PRICE_ANOMALY_ENABLED=False):
            room = make_room(self._owner(), "Disabled", price=20000)
            self.assertIsNone(get_price_anomaly(room))

    @override_settings(PRICE_ANOMALY_ENABLED=True)
    def test_list_response_has_nullable_field(self):
        # With < MIN_ROOMS available rooms there is no trained model, so the
        # field must render as null rather than crash the list endpoint.
        owner = self._owner()
        make_room(owner, "Only Room", price=9000)
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("price_anomaly", res.data["results"][0])
        self.assertIsNone(res.data["results"][0]["price_anomaly"])

    _seq = 0

    def _owner(self):
        PriceAnomalyTests._seq += 1
        return User.objects.create_user(
            username=f"pa_user_{PriceAnomalyTests._seq}",
            email=f"pa_user_{PriceAnomalyTests._seq}@example.com",
            password="test12345",
        )


class FallbackTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="fb", email="fb@example.com", password="test12345"
        )
        self.room_a = make_room(self.landlord, "Fallback Room A", area="Gulshan")
        self.room_b = make_room(self.landlord, "Fallback Room B", area="Gulshan")

    @override_settings(SEMANTIC_SEARCH_ENABLED=False)
    def test_disabled_semantic_uses_legacy_tfidf_path(self):
        # The flag off -> legacy semantic_candidates path still runs and
        # ranks; search keeps working with nl_parsed attached.
        res = self.client.get("/api/v1/rooms/?q=gulshan&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 2)
        self.assertIn("nl_parsed", res.data)

    def test_all_ranking_legs_fail_falls_back_to_default_order(self):
        # Both the TF-IDF and embedding legs unavailable -> the smart path
        # keeps default ordering instead of 500ing.
        with (
            patch("rooms.views.hybrid_rank", return_value=None),
            patch("rooms.views.semantic_candidates", return_value=None),
        ):
            res = self.client.get("/api/v1/rooms/?q=gulshan&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 2)
        self.assertIn("nl_parsed", res.data)

    def test_rank_metadata_debug_only(self):
        res = self.client.get("/api/v1/rooms/?q=gulshan&smart=1&debug_rank=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("rank_meta", res.data)
        first_id = res.data["results"][0]["id"]
        # rank_meta is keyed by room id (int) in the unrendered response data.
        self.assertIn("final_score", res.data["rank_meta"][first_id])

        # Without the debug param (and DEBUG off in tests), no metadata leaks.
        res = self.client.get("/api/v1/rooms/?q=gulshan&smart=1")
        self.assertNotIn("rank_meta", res.data)
