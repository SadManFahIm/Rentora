"""Tests for the Tier-3 RAG listing Q&A — grounded answers over one listing.

The key property under test: the Copilot can only ever assert facts that
exist on the listing row. It must refuse questions it has no data for, and
never invent a price, amenity or claim.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from copilot.listing_qa import listing_answer, listing_facts
from copilot.services import chat, listing_facts_for
from rooms.models import Room

User = get_user_model()


def make_room(
    owner,
    title="Bright Studio, Dhanmondi",
    area="Dhanmondi",
    room_type="studio",
    price=14000,
    amenities=None,
    verified=True,
):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A bright furnished studio near Rapa Plaza with attached bath.",
        room_type=room_type,
        price=price,
        area=area,
        address="Road 6, Dhanmondi",
        lat=23.7461,
        lng=90.3762,
        amenities=amenities or ["wifi", "furnished", "attached bath"],
        size_sqft=320,
        verified=verified,
    )


class ListingAnswerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="rag_owner", email="rag_owner@example.com", password="test12345"
        )
        self.room = make_room(self.owner)

    def test_price_question_uses_real_price(self):
        out = listing_answer("rent কত?", self.room)
        self.assertEqual(out["aspect"], "price")
        self.assertIn("14,000", out["text"])
        self.assertIn(self.room.title, out["text"])

    def test_amenities_question_lists_real_amenities(self):
        out = listing_answer("কি সুবিধা আছে?", self.room)
        self.assertEqual(out["aspect"], "amenities")
        self.assertIn("wifi", out["text"])
        self.assertIn("furnished", out["text"])

    def test_area_question_uses_real_area_and_address(self):
        out = listing_answer("where is it located?", self.room)
        self.assertEqual(out["aspect"], "area")
        self.assertIn("Dhanmondi", out["text"])

    def test_verified_question(self):
        out = listing_answer("is this verified?", self.room)
        self.assertEqual(out["aspect"], "verified")
        self.assertIn("verified", out["text"].lower())

    def test_unanswerable_question_refused(self):
        out = listing_answer("what's the landlord's phone number?", self.room)
        self.assertEqual(out["aspect"], None)
        self.assertIn("can only answer from this listing", out["text"])

    def test_no_aspect_falls_back_to_summary(self):
        out = listing_answer("এটা সম্পর্কে বলো", self.room)
        self.assertEqual(out["aspect"], "summary")
        self.assertIn(self.room.title, out["text"])
        self.assertIn("14,000", out["text"])

    def test_never_invents_unknown_amenity(self):
        # "gym" is not in this listing — the answer must not claim it.
        out = listing_answer("is there a gym?", self.room)
        self.assertNotIn("gym is included", out["text"].lower())
        self.assertNotIn("gym", [a.lower() for a in self.room.amenities])


class ListingFactsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="facts_owner", email="facts_owner@example.com", password="test12345"
        )

    def test_facts_are_public_fields_only(self):
        room = make_room(self.owner)
        facts = listing_facts(room)
        self.assertEqual(facts["id"], room.pk)
        self.assertEqual(facts["price"], float(room.price))
        self.assertEqual(facts["area"], "Dhanmondi")
        self.assertTrue(facts["verified"])
        self.assertIn("wifi", facts["amenities"])
        # Never leaks owner/private data.
        for forbidden in ("owner", "contact", "phone", "email"):
            self.assertNotIn(forbidden, facts)

    def test_missing_listing_returns_none(self):
        self.assertIsNone(listing_facts_for(999999))

    def test_unavailable_listing_returns_none(self):
        room = make_room(self.owner, verified=False)
        room.is_available = False
        room.save()
        self.assertIsNone(listing_facts_for(room.pk))


class ListingChatTests(TestCase):
    """chat() in listing mode is grounded and never falls into search mode."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="lc_owner", email="lc_owner@example.com", password="test12345"
        )
        self.room = make_room(self.owner)

    def test_listing_mode_answers_grounded(self):
        res = chat("দাম কত?", None, None, listing_id=self.room.pk)
        self.assertEqual(res["mode"], "listing")
        self.assertEqual(res["listing"]["id"], self.room.pk)
        self.assertIn("14,000", res["message"])

    def test_listing_mode_never_returns_other_listings(self):
        other = make_room(self.owner, title="Other Room", price=8000)
        res = chat("কি সুবিধা আছে?", None, None, listing_id=self.room.pk)
        self.assertEqual(res["mode"], "listing")
        self.assertEqual(res["listings"], [])
        self.assertNotIn(other.title, res["message"])

    def test_missing_listing_graceful(self):
        res = chat("দাম কত?", None, None, listing_id=999999)
        self.assertEqual(res["mode"], "listing")
        self.assertIsNone(res["listing"])
        self.assertIn("couldn't find", res["message"])

    def test_search_mode_still_defaults(self):
        res = chat("Uttara room", None, None)
        self.assertEqual(res["mode"], "search")


class ListingFactsApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="lf_owner", email="lf_owner@example.com", password="test12345"
        )
        self.room = make_room(self.owner)

    def test_facts_endpoint_public(self):
        res = self.client.get(f"/api/v1/copilot/listing/{self.room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.room.pk)
        self.assertIn("amenities", res.data)
        self.assertNotIn("owner", res.data)

    def test_facts_endpoint_404_for_missing(self):
        res = self.client.get("/api/v1/copilot/listing/999999/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_chat_with_listing_id_via_api(self):
        res = self.client.post(
            "/api/v1/copilot/chat/",
            {"message": "দাম কত?", "listing_id": self.room.pk},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["mode"], "listing")
        self.assertEqual(res.data["listing"]["id"], self.room.pk)
