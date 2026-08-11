"""Phase 11 room tests — smart search, NL parsing, image search, ranking.

Covers the Search & Discovery features: hybrid semantic ranking (`smart=1`),
Bangla/English natural-language parsing (`nl_parsed` in the list response),
perceptual-hash image similarity (`/rooms/<id>/similar-images/`), personal
boost ordering from view/wishlist history, and the expanded Dhaka gazetteer.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room, RoomImage
from rooms.nl_query import parse_bangla_number, parse_nl_query
from rooms.streets import search_streets
from wishlist.models import Wishlist

User = get_user_model()


def make_room(
    owner,
    title,
    area="Mirpur",
    price=9000,
    room_type="single",
    description="A cozy room near the university.",
    gender="any",
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
    )


class NlParserTests(APITestCase):
    def test_bangla_digits_and_words(self):
        self.assertEqual(parse_bangla_number("১০"), 10)
        self.assertEqual(parse_bangla_number("১২,৫০০"), 12500)
        self.assertEqual(parse_bangla_number("10k"), 10000)

    def test_bangla_budget_and_area(self):
        parsed = parse_nl_query("১০ হাজার এর মধ্যে uttara room")
        self.assertEqual(parsed["budget_max"], 10000)
        self.assertIn("Uttara", parsed["areas"])
        self.assertTrue(any("10,000" in h for h in parsed["hints"]))

    def test_english_budget_type_gender_month(self):
        parsed = parse_nl_query("৳12000 gulshan single male, july move-in")
        self.assertEqual(parsed["budget_max"], 12000)
        self.assertIn("Gulshan", parsed["areas"])
        self.assertEqual(parsed["room_type"], "single")
        self.assertEqual(parsed["gender"], "male")
        self.assertIn("July", parsed["months"])

    def test_bangla_month(self):
        parsed = parse_nl_query("জুলাই থেকে move-in dhanmondi")
        self.assertIn("July", parsed["months"])
        self.assertIn("Dhanmondi", parsed["areas"])

    def test_no_match_yields_keyword_hint(self):
        parsed = parse_nl_query("some random query text")
        self.assertEqual(parsed["hints"], ["keyword search"])


class SmartSearchTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="p11", email="p11@example.com", password="test12345"
        )
        # A small but realistic corpus: several rooms across areas so the
        # TF-IDF + LSA space has enough structure to rank meaningfully.
        self.room_a = make_room(
            self.landlord,
            "Sunny Studio in Gulshan",
            area="Gulshan",
            price=15000,
            description="Bright furnished studio apartment with balcony near the shops.",
        )
        self.room_b = make_room(
            self.landlord,
            "Gulshan Guest Room",
            area="Gulshan",
            price=8000,
            description="Simple guest room with a basic bed and shared bathroom.",
        )
        self.room_c = make_room(
            self.landlord,
            "Mirpur Family Flat",
            area="Mirpur",
            price=18000,
            description="Three-bedroom family apartment, fully furnished with balcony.",
            room_type="studio",
        )
        self.room_d = make_room(
            self.landlord,
            "Dhanmondi Student Room",
            area="Dhanmondi",
            price=5500,
            description="Cheap single room for students, walking distance to campus.",
        )
        self.room_e = make_room(
            self.landlord,
            "Uttara Executive Flat",
            area="Uttara",
            price=25000,
            description="Executive two-bedroom flat, modern interior, near the metro.",
            room_type="studio",
        )

    def test_smart_reranks_keyword_results(self):
        # Plain keyword search returns newest-first (A then B by created_at —
        # same owner, so tie on tier/verified; A is newer here).
        res = self.client.get("/api/v1/rooms/?q=gulshan")
        self.assertEqual(res.data["count"], 2)

        # Smart search ranks the *semantically closer* match first: a query
        # about a furnished balcony apartment in Gulshan should surface
        # room_a ("furnished", "balcony", "apartment") above room_b.
        res = self.client.get("/api/v1/rooms/?q=gulshan furnished balcony apartment&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 2)
        self.assertEqual(res.data["results"][0]["id"], self.room_a.id)
        self.assertIn("nl_parsed", res.data)

    def test_smart_discovers_keyword_misses(self):
        # "student room near campus" shares no literal token with room_d's
        # text either, so plain keyword search misses everything.
        res = self.client.get("/api/v1/rooms/?q=student room near campus")
        self.assertEqual(res.data["count"], 0)

        # Semantic ranking still surfaces the closest rooms (the student
        # room in Dhanmondi should be among them, if not first).
        res = self.client.get("/api/v1/rooms/?q=student room near campus&smart=1")
        self.assertGreaterEqual(res.data["count"], 1)
        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(self.room_d.id, ids)

    def test_smart_applies_nl_filters(self):
        # "১০ হাজার এর মধ্যে gulshan" -> budget ≤ 10,000 in Gulshan: only
        # room_b qualifies; the ৳15,000 studio is excluded by budget, not by
        # relevance.
        res = self.client.get("/api/v1/rooms/?q=১০ হাজার এর মধ্যে gulshan&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["id"], self.room_b.id)
        self.assertEqual(res.data["nl_parsed"]["budget_max"], 10000)

    def test_smart_falls_back_when_semantic_unavailable(self):
        # sklearn hiccup -> no semantic ordering, no 500. NL parsing still
        # runs (nl_parsed stays attached) but results keep default ordering.
        with patch("rooms.views.semantic_candidates", return_value=None):
            res = self.client.get("/api/v1/rooms/?q=gulshan&smart=1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 2)
        self.assertIn("nl_parsed", res.data)


@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(prefix="rentora_img_"),
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
)
class ImageSearchTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="img1", email="img1@example.com", password="test12345"
        )
        self.room_a = make_room(self.landlord, "Photo A", area="Dhanmondi")
        self.room_b = make_room(self.landlord, "Photo B", area="Dhanmondi")
        self.room_c = make_room(self.landlord, "Photo C", area="Mirpur")
        self._attach_image(self.room_a, self._gray(), "a.png")
        # Photo B is byte-for-byte identical to A (same flat gray) -> distance 0.
        self._attach_image(self.room_b, self._gray(), "b.png")
        # Photo C is a checkerboard — a very different bit pattern.
        self._attach_image(self.room_c, self._checkerboard(), "c.png")

    def _attach_image(self, room, buf, name):
        RoomImage.objects.create(
            room=room, is_primary=True, image=SimpleUploadedFile(name, buf, "image/png")
        )

    @staticmethod
    def _gray():
        from io import BytesIO

        buffer = BytesIO()
        Image.new("RGB", (64, 64), (128, 128, 128)).save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def _checkerboard():
        from io import BytesIO

        buffer = BytesIO()
        img = Image.new("RGB", (64, 64))
        for y in range(64):
            for x in range(64):
                img.putpixel((x, y), (255, 255, 255) if (x // 8 + y // 8) % 2 == 0 else (0, 0, 0))
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_similar_images_finds_lookalikes(self):
        res = self.client.get(f"/api/v1/rooms/{self.room_a.id}/similar-images/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in res.data]
        self.assertIn(self.room_b.id, ids)
        self.assertNotIn(self.room_c.id, ids)

    def test_similar_images_public_and_ordered(self):
        res = self.client.get(f"/api/v1/rooms/{self.room_a.id}/similar-images/?limit=4")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        distances = [item["phash_distance"] for item in res.data]
        self.assertEqual(distances, sorted(distances))


class PersonalBoostTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="boostl", email="boostl@example.com", password="test12345"
        )
        self.viewer = User.objects.create_user(
            username="boostv", email="boostv@example.com", password="test12345"
        )
        self.room_a = make_room(self.landlord, "Boost A", area="Dhanmondi")
        self.room_b = make_room(self.landlord, "Boost B", area="Dhanmondi")

    def test_viewed_room_ranks_first_for_authenticated_user(self):
        from rooms.models import RoomView

        RoomView.objects.create(room=self.room_a, viewer=self.viewer)
        self.client.force_authenticate(self.viewer)
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.data["results"][0]["id"], self.room_a.id)

    def test_wishlisted_room_ranks_above_untouched(self):
        Wishlist.objects.create(user=self.viewer, room=self.room_b)
        self.client.force_authenticate(self.viewer)
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.data["results"][0]["id"], self.room_b.id)

    def test_anonymous_keeps_default_order(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Newest first by default (no boost annotation to crash on).
        self.assertEqual(res.data["results"][0]["id"], self.room_b.id)


class DhakaGazetteerTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="gaz", email="gaz@example.com", password="test12345"
        )

    def test_new_area_choices_are_valid(self):
        room = make_room(self.landlord, "Uttara Flat", area=Room.Area.UTTARA)
        self.assertEqual(room.area, "Uttara")
        room2 = make_room(self.landlord, "Bashundhara Flat", area=Room.Area.BASHUNDHARA)
        self.assertEqual(room2.area, "Bashundhara")

    def test_area_filter_accepts_new_areas(self):
        make_room(self.landlord, "Uttara Flat", area=Room.Area.UTTARA)
        res = self.client.get("/api/v1/rooms/?area=Uttara")
        self.assertEqual(res.data["count"], 1)

    def test_new_streets_searchable(self):
        for query, expected_key in [
            ("tongi", "tongi"),
            ("badda link", "badda_link_road"),
            ("bashundhara", "bashundhara"),
            ("uttara sector 10", "uttara_sector_10"),
        ]:
            hits = search_streets(query)
            self.assertTrue(
                any(s.key == expected_key for s in hits), f"{query!r} missing {expected_key}"
            )
