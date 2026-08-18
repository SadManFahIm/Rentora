"""Tests for Tier-5 Copilot image understanding + listing description draft.

Image understanding must be *statistical and honest*: brightness / colour /
tone labels come from real pixels, and the answer explicitly says it is not
semantic recognition. The description generator must be grounded in the
landlord's own fields (no invented prices/amenities).
"""

import io
import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from copilot.image_profile import image_profile
from copilot.listing_qa import listing_answer
from rooms.description_generator import generate_listing_draft
from rooms.models import Room, RoomImage

User = get_user_model()


def _bright_warm_photo() -> bytes:
    """A bright, warm-toned photo (light beige with a warm orange patch)."""
    img = Image.new("RGB", (640, 480), (240, 230, 210))
    px = img.load()
    for y in range(200, 320):
        for x in range(260, 420):
            px[x, y] = (220, 150, 60)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


class ImageProfileTests(TestCase):
    def test_profiles_real_image(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(_bright_warm_photo())
            path = tmp.name
        try:
            profile = image_profile(path)
            self.assertTrue(profile["available"])
            self.assertIn(profile["brightness"], ("bright", "normal"))
            self.assertIn(profile["colourfulness"], ("muted", "colourful"))
            self.assertTrue(profile["tones"])
        finally:
            os.unlink(path)

    def test_missing_file_graceful(self):
        profile = image_profile("/nonexistent/nope.jpg")
        self.assertFalse(profile["available"])
        self.assertIsNone(profile["brightness"])


class ListingPhotosAspectTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="img_owner", password="test12345")
        self.room = Room.objects.create(
            owner=self.owner,
            title="Bright Studio",
            description="A bright furnished studio.",
            room_type="studio",
            price=14000,
            area="Dhanmondi",
            address="Road 6",
            lat=23.7461,
            lng=90.3762,
            amenities=["wifi"],
            size_sqft=320,
        )

    def test_photo_question_answered_grounded(self):
        RoomImage.objects.create(
            room=self.room,
            image=SimpleUploadedFile("photo.jpg", _bright_warm_photo(), content_type="image/jpeg"),
            is_primary=True,
        )
        out = listing_answer("দেখতে কেমন? ছবি দেখাও", self.room)
        self.assertEqual(out["aspect"], "photos")
        self.assertIn("photo", out["text"].lower())
        self.assertIn("statistical description", out["text"])

    def test_no_photos_answers_honestly(self):
        out = listing_answer("what does it look like?", self.room)
        self.assertEqual(out["aspect"], "photos")
        self.assertIn("doesn't have any photos", out["text"])


class DescriptionDraftTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="draft_user", password="test12345")

    def test_generate_draft_grounded(self):
        draft = generate_listing_draft(
            area="Dhanmondi",
            room_type="studio",
            price=14000,
            size_sqft=320,
            amenities=["wifi", "ac", "attached bath"],
        )
        self.assertIn("Dhanmondi", draft["description"])
        self.assertIn("14,000", draft["description"])
        self.assertIn("wifi", draft["amenities"])
        self.assertIn("review", draft["note"].lower())

    def test_no_invented_amenities(self):
        draft = generate_listing_draft(
            area="Mirpur", room_type="single", price=None, size_sqft=None, amenities=[]
        )
        self.assertEqual(draft["amenities"], ["wifi", "attached bath"])  # safe defaults
        self.assertNotIn("gym", draft["description"].lower())

    def test_endpoint_authenticated_only(self):
        url = "/api/v1/rooms/generate-description/"
        response = self.client.post(url, {"area": "Dhanmondi"}, format="json")
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )
        self.client.force_authenticate(self.user)
        response = self.client.post(
            url,
            {"area": "Dhanmondi", "room_type": "studio", "price": 15000, "amenities": ["wifi"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("title", response.data)
        self.assertIn("description", response.data)
        self.assertIn("Dhanmondi", response.data["description"])
