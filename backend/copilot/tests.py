"""Tests for Rentora Copilot (Phase 11 — conversational room discovery).

Covers intent extraction (Bangla/English/mixed), follow-up context, the
hallucination guard (every listing in an answer exists in the DB and obeys
the hard filters), no-result handling, greetings/reset, and the API contract.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from copilot.services import chat, extract_intent, merge_intent, retrieve_rooms
from rooms.models import Room

User = get_user_model()


def make_user(username="tenant", nid_verified=True):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        nid_verified=nid_verified,
    )


def make_room(
    owner,
    title="Student Room, Uttara Sector 10",
    area="Uttara",
    room_type="single",
    price=9000,
    amenities=None,
):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="Affordable student room close to the university and market.",
        room_type=room_type,
        price=price,
        area=area,
        address="Sector 10, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=amenities or ["wifi", "furnished"],
        size_sqft=220,
    )


class IntentExtractionTests(TestCase):
    def test_bangla_query_parses_budget_and_area(self):
        intent = extract_intent("Uttara-তে ১০ হাজারের মধ্যে student room চাই")
        self.assertEqual(intent["areas"], ["Uttara"])
        self.assertEqual(intent["budget_max"], 10000)
        # "student room" is a semantic concept, not a room_type enum — the
        # query text still steers semantic ranking (never a hard filter).
        self.assertIsNone(intent["room_type"])

    def test_room_type_words_parsed(self):
        intent = extract_intent("single room in Mirpur")
        self.assertEqual(intent["room_type"], "single")

    def test_english_query_parses_area_and_price(self):
        intent = extract_intent("furnished studio in Dhanmondi under 15k")
        self.assertEqual(intent["areas"], ["Dhanmondi"])
        self.assertEqual(intent["budget_max"], 15000)
        self.assertEqual(intent["room_type"], "studio")
        self.assertIn("Furnished", intent["amenities"])

    def test_mixed_banglish_query(self):
        intent = extract_intent("mirpur e single room, AC, budget ৮ হাজার")
        self.assertIn("Mirpur", intent["areas"])
        self.assertEqual(intent["budget_max"], 8000)
        self.assertEqual(intent["room_type"], "single")
        self.assertIn("AC", intent["amenities"])

    def test_amenity_extraction(self):
        intent = extract_intent("pet friendly room with parking and kitchen")
        for amenity in ("Pet Friendly", "Parking", "Kitchen"):
            self.assertIn(amenity, intent["amenities"])

    def test_property_words_are_hints_not_filters(self):
        intent = extract_intent("basah/flat in Banani")
        self.assertIn("Banani", intent["areas"])
        self.assertTrue(any(w in intent["property_words"] for w in ("flat", "basa")))


class MergeIntentTests(TestCase):
    def test_followup_preserves_prior_constraints(self):
        stored = {
            "budget_max": 10000,
            "areas": ["Uttara"],
            "room_type": None,
            "gender": None,
            "months": [],
            "amenities": [],
            "property_words": [],
            "hints": ["Budget ≤ ৳10,000"],
        }
        fresh = extract_intent("শুধু furnished দেখাও")
        merged = merge_intent(stored, fresh)
        self.assertEqual(merged["budget_max"], 10000)
        self.assertEqual(merged["areas"], ["Uttara"])
        self.assertIn("Furnished", merged["amenities"])

    def test_fresh_constraints_override_stored(self):
        stored = {"budget_max": 10000, "areas": ["Uttara"], "amenities": []}
        fresh = extract_intent("Dhanmondi-তে দেখাও")
        merged = merge_intent(stored, fresh)
        self.assertEqual(merged["areas"], ["Dhanmondi"])
        self.assertEqual(merged["budget_max"], 10000)  # untouched budget survives


class RetrievalTests(TestCase):
    def setUp(self):
        self.owner = make_user("landlord")
        self.uttara_cheap = make_room(self.owner, price=8500, amenities=["wifi", "furnished"])
        self.uttara_expensive = make_room(self.owner, title="Premium Room", price=18000)
        self.dhanmondi_cheap = make_room(
            self.owner, title="Dhanmondi Studio", area="Dhanmondi", room_type="studio", price=9000
        )

    def test_hard_filters_never_violated(self):
        intent = {
            "budget_max": 10000,
            "areas": ["Uttara"],
            "room_type": None,
            "gender": None,
            "amenities": [],
            "property_words": [],
        }
        rooms, total, kind = retrieve_rooms(intent, None)
        self.assertEqual(kind, "match")
        self.assertEqual(total, 1)
        self.assertEqual(rooms[0].pk, self.uttara_cheap.pk)

    def test_no_match_returns_none_kind(self):
        intent = {
            "budget_max": 5000,
            "areas": ["Gulshan"],
            "room_type": None,
            "gender": None,
            "amenities": [],
            "property_words": [],
        }
        rooms, total, kind = retrieve_rooms(intent, None)
        self.assertEqual(kind, "none")
        self.assertEqual(total, 0)
        self.assertEqual(rooms, [])


class ChatTests(TestCase):
    def setUp(self):
        self.owner = make_user("landlord")
        self.room = make_room(
            self.owner, price=8500, amenities=["wifi", "furnished", "attached bath"]
        )
        cache.clear()

    def test_bangla_chat_returns_database_backed_listings(self):
        res = chat("Uttara-তে ১০ হাজারের মধ্যে room", None, None)
        self.assertGreaterEqual(res["total_count"], 1)
        for listing in res["listings"]:
            self.assertTrue(Room.objects.filter(pk=listing["id"]).exists())
            self.assertLessEqual(listing["price"], 10000)
            self.assertEqual(listing["area"], "Uttara")
        # No hallucination: the message mentions only returned rooms.
        self.assertIn("matching room", res["message"])
        self.assertIn(self.room.title, res["message"])

    def test_no_result_does_not_fabricate(self):
        res = chat("Gulshan-এ ৩ হাজারের মধ্যে", None, None)
        self.assertEqual(res["total_count"], 0)
        self.assertEqual(res["listings"], [])
        self.assertIn("couldn't find", res["message"])

    def test_followup_keeps_context(self):
        r1 = chat("Uttara-তে ১০ হাজারের মধ্যে room", None, None)
        sid = r1["session_id"]
        r2 = chat("furnished দেখাও", sid, None)
        self.assertEqual(r2["intent"]["areas"], ["Uttara"])
        self.assertEqual(r2["intent"]["budget_max"], 10000)
        self.assertIn("Furnished", r2["intent"]["amenities"])

    def test_greeting_returns_welcome(self):
        res = chat("hi", None, None)
        self.assertIn("I'm Rentora Copilot", res["message"])

    def test_reset_clears_session(self):
        r1 = chat("Uttara-তে ১০ হাজারের মধ্যে room", None, None)
        sid = r1["session_id"]
        r2 = chat("reset", sid, None)
        self.assertEqual(r2["intent"]["areas"], [])
        self.assertIsNone(r2["intent"]["budget_max"])

    def test_empty_message_returns_prompt(self):
        res = chat("   ", None, None)
        self.assertIn("looking for", res["message"])

    def test_english_chat_works(self):
        res = chat("student room in Uttara under 10000", None, None)
        self.assertGreaterEqual(res["total_count"], 1)

    @override_settings(COPILOT_MAX_RESULTS=3)
    def test_max_results_capped(self):
        for i in range(5):
            make_room(self.owner, title=f"Extra Room {i}", price=8000)
        res = chat("Uttara room", None, None)
        self.assertLessEqual(len(res["listings"]), 3)


class CopilotApiTests(APITestCase):
    def setUp(self):
        self.owner = make_user("landlord")
        make_room(self.owner, price=8500)

    def test_chat_endpoint_public_and_structured(self):
        res = self.client.post("/api/v1/copilot/chat/", {"message": "Uttara room"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("session_id", res.data)
        self.assertIn("message", res.data)
        self.assertIn("intent", res.data)
        self.assertIn("listings", res.data)
        self.assertIn("suggestions", res.data)

    def test_empty_message_rejected(self):
        res = self.client.post("/api/v1/copilot/chat/", {"message": ""}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_allowed(self):
        # Copilot is public like the rooms list — no auth required.
        res = self.client.post("/api/v1/copilot/chat/", {"message": "hello"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    @override_settings(COPILOT_ENABLED=False)
    def test_disabled_flag_returns_503(self):
        res = self.client.post("/api/v1/copilot/chat/", {"message": "hello"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
