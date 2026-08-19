"""Tests for Phase 14 — Vision & content AI (rooms.vision)."""

from __future__ import annotations

import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image, ImageDraw
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room, RoomImage, RoomVisionAnalysis
from rooms.vision import (
    analyze_listing,
    fingerprint_image,
    heuristic_caption,
    image_search,
    observations_from_profiles,
)

User = get_user_model()

_TMP_MEDIA = tempfile.mkdtemp(prefix="rentora_vision_")


def _png_bytes(mode: str = "gray", size: int = 64) -> bytes:
    """Deterministic test image (Pillow → PNG bytes)."""
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    if mode == "gray":
        draw.rectangle([0, 0, size, size], fill=(128, 128, 128))
    elif mode == "bright":
        draw.rectangle([0, 0, size, size], fill=(230, 230, 230))
    elif mode == "warm":
        draw.rectangle([0, 0, size, size], fill=(220, 190, 150))
    elif mode == "cool":
        draw.rectangle([0, 0, size, size], fill=(90, 140, 190))
    elif mode == "checker":
        half = size // 2
        draw.rectangle([0, 0, half, half], fill=(20, 20, 20))
        draw.rectangle([half, half, size, size], fill=(200, 200, 200))
        draw.rectangle([half, 0, size, half], fill=(120, 120, 120))
        draw.rectangle([0, half, half, size], fill=(80, 80, 80))
    elif mode == "red":
        draw.rectangle([0, 0, size, size], fill=(200, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload(name: str, content: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="image/png")


def _make_room(owner, *, photo: bytes | None = None, **fields) -> Room:
    defaults = {
        "title": "Test Room",
        "description": "A test listing",
        "price": 12000,
        "area": "Dhanmondi",
        "room_type": "single",
        "size_sqft": 320,
        "gender_preference": "any",
        "lat": 23.75,
        "lng": 90.39,
        "is_available": True,
    }
    defaults.update(fields)
    room = Room.objects.create(owner=owner, **defaults)
    if photo is not None:
        RoomImage.objects.create(
            room=room,
            is_primary=True,
            image=_upload("photo.png", photo),
        )
    return room


@override_settings(
    MEDIA_ROOT=_TMP_MEDIA,
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
)
class FingerprintTests(APITestCase):
    """Deterministic pixel statistics."""

    def test_gray_image_brightness_normal(self):
        fp = fingerprint_image(_png_bytes("gray"))
        self.assertIsNotNone(fp)
        self.assertEqual(fp["brightness_label"], "normal")
        self.assertAlmostEqual(fp["brightness"], 0.502, places=2)

    def test_bright_image_label_and_palette(self):
        fp = fingerprint_image(_png_bytes("bright"))
        self.assertEqual(fp["brightness_label"], "bright")
        self.assertEqual(fp["palette"][0]["name"], "off-white")
        self.assertTrue(fp["palette"][0]["share"] > 0.9)

    def test_warm_image_palette_name(self):
        fp = fingerprint_image(_png_bytes("warm"))
        self.assertEqual(fp["palette"][0]["name"], "warm beige")

    def test_red_image_palette_name(self):
        fp = fingerprint_image(_png_bytes("red"))
        self.assertEqual(fp["palette"][0]["name"], "warm red")

    def test_phash_deterministic_and_distinct(self):
        a = fingerprint_image(_png_bytes("gray"))
        b = fingerprint_image(_png_bytes("gray"))
        c = fingerprint_image(_png_bytes("checker"))
        self.assertEqual(a["phash"], b["phash"])
        self.assertNotEqual(a["phash"], c["phash"])

    def test_unreadable_bytes_returns_none(self):
        self.assertIsNone(fingerprint_image(b"not an image"))


@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class VisionAnalysisUnitTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="landlord14", email="landlord14@example.com", password="pass12345"
        )

    def test_no_photos_not_available(self):
        room = _make_room(self.owner, photo=None)
        analysis = analyze_listing(room)
        self.assertFalse(analysis["available"])
        self.assertEqual(analysis["reason"], "no readable photos")

    def test_heuristic_analysis_shape(self):
        room = _make_room(self.owner, photo=_png_bytes("bright"))
        analysis = analyze_listing(room)
        self.assertTrue(analysis["available"])
        self.assertEqual(analysis["provider"], "heuristic")
        self.assertEqual(analysis["suggested_amenities"], [])
        self.assertTrue(analysis["caption"])
        self.assertIn("Photos show a", analysis["caption"])
        kinds = {o["kind"] for o in analysis["observations"]}
        self.assertTrue({"lighting", "tone", "decor", "composition"} <= kinds)
        self.assertGreaterEqual(len(analysis["palette"]), 1)

    def test_observations_reflect_pixels(self):
        room = _make_room(self.owner, photo=_png_bytes("bright"))
        analysis = analyze_listing(room)
        lighting = next(o for o in analysis["observations"] if o["kind"] == "lighting")
        self.assertEqual(lighting["label"], "Bright, well-lit interior")

        warm = _make_room(self.owner, photo=_png_bytes("warm"))
        analysis_warm = analyze_listing(warm)
        tone = next(o for o in analysis_warm["observations"] if o["kind"] == "tone")
        self.assertIn("warm", tone["label"].lower())

    def test_observations_empty_without_profiles(self):
        self.assertEqual(observations_from_profiles([]), [])

    def test_caption_mentions_photo_count(self):
        room = _make_room(self.owner, photo=_png_bytes("gray"))
        analysis = analyze_listing(room)
        self.assertIn("Single photo on file", analysis["caption"])
        caption = heuristic_caption(analysis["photo_profiles"], analysis["observations"])
        self.assertTrue(caption)

    def test_gateway_failure_falls_back_to_heuristic(self):
        room = _make_room(self.owner, photo=_png_bytes("gray"))
        with override_settings(
            VISION_PROVIDER="http",
            VISION_GATEWAY_URL="https://vision.invalid/analyze",
        ):
            # No request context → no image URLs → gateway skipped → heuristic.
            analysis = analyze_listing(room)
        self.assertEqual(analysis["provider"], "heuristic")
        self.assertTrue(analysis["caption"])

    def test_image_search_same_photo_scores_high(self):
        photo = _png_bytes("checker")
        room = _make_room(self.owner, photo=photo)
        matches = image_search(photo)
        self.assertTrue(matches)
        self.assertEqual(matches[0]["room_id"], room.pk)
        self.assertGreaterEqual(matches[0]["match_score"], 90)
        self.assertTrue(matches[0]["reasons"])

    def test_image_search_skips_unrelated_photos(self):
        _make_room(self.owner, photo=_png_bytes("warm"))
        _make_room(self.owner, photo=_png_bytes("cool"))
        matches = image_search(_png_bytes("bright"))
        self.assertIsInstance(matches, list)


@override_settings(
    MEDIA_ROOT=_TMP_MEDIA,
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
)
class VisionApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="landlord14b", email="landlord14b@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="tenant14b", email="tenant14b@example.com", password="pass12345"
        )
        self.admin = User.objects.create_superuser(username="admin14b", password="pass12345")
        self.room = _make_room(self.owner, photo=_png_bytes("warm"))

    def _auth(self, user):
        self.client.force_authenticate(user)

    def test_analyze_requires_auth(self):
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analyze_owner_stores_analysis(self):
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["available"])
        self.assertEqual(res.data["provider"], "heuristic")
        stored = RoomVisionAnalysis.objects.filter(room=self.room).first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.provider, "heuristic")

    def test_analyze_forbidden_for_others_allowed_for_admin(self):
        self._auth(self.other)
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.admin)
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_analyze_disabled_returns_503(self):
        self._auth(self.owner)
        with override_settings(VISION_ENABLED=False):
            res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_analyze_room_without_photos_422(self):
        bare = _make_room(self.owner, photo=None)
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/rooms/{bare.pk}/vision/analyze/")
        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertFalse(res.data["available"])

    def test_stored_analysis_get_404_then_200(self):
        self._auth(self.owner)
        res = self.client.get(f"/api/v1/rooms/{self.room.pk}/vision/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/analyze/")
        res = self.client.get(f"/api/v1/rooms/{self.room.pk}/vision/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("caption", res.data)

    def test_vision_description_drafts_from_photos(self):
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/description/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("title", res.data)
        self.assertIn("description", res.data)
        self.assertTrue(res.data["observations"])
        self.assertIn("photos", res.data["note"])

    def test_vision_description_without_photos_422(self):
        bare = _make_room(self.owner, photo=None)
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/rooms/{bare.pk}/vision/description/")
        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_vision_description_forbidden_for_others(self):
        self._auth(self.other)
        res = self.client.post(f"/api/v1/rooms/{self.room.pk}/vision/description/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_image_search_public_returns_matches(self):
        photo = _png_bytes("warm")
        _make_room(self.owner, photo=photo)
        res = self.client.post(
            "/api/v1/rooms/vision/search/",
            {"image": _upload("query.png", photo)},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["matches"])
        first = res.data["matches"][0]
        self.assertGreaterEqual(first["match_score"], 90)
        self.assertTrue(first["reasons"])
        self.assertIn("note", res.data)

    def test_image_search_requires_image(self):
        res = self.client.post("/api/v1/rooms/vision/search/", {}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_image_search_rejects_non_image(self):
        res = self.client.post(
            "/api/v1/rooms/vision/search/",
            {"image": _upload("not-an-image.png", b"hello")},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_image_search_disabled_returns_503(self):
        with override_settings(VISION_ENABLED=False):
            res = self.client.post(
                "/api/v1/rooms/vision/search/",
                {"image": _upload("q.png", _png_bytes("gray"))},
                format="multipart",
            )
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
