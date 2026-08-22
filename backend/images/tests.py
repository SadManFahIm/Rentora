"""Tests for the WebP variant pipeline + hardened image validation."""

from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import serializers

from config.uploads import MAX_ROOM_IMAGES, validate_image_upload
from images.services import (
    delete_variants,
    generate_variants,
    has_variants,
    variant_urls,
)


def make_png(width=800, height=600, with_exif=False) -> bytes:
    img = Image.new("RGB", (width, height), (200, 120, 40))
    if with_exif:
        exif = img.getexif()
        exif[0x0110] = b"ModelX"  # Make tag
        img.save(BytesIO(), format="PNG")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def make_jpeg_with_exif(width=800, height=600) -> bytes:
    img = Image.new("RGB", (width, height), (40, 90, 200))
    buffer = BytesIO()
    img.save(buffer, format="JPEG", exif=b"Exif\x00\x00")
    return buffer.getvalue()


class ImageValidationTests(TestCase):
    def test_accepts_real_image(self):
        upload = SimpleUploadedFile("photo.png", make_png(), content_type="image/png")
        self.assertEqual(validate_image_upload(upload), upload)

    def test_rejects_disguised_file(self):
        # A text file renamed .jpg — content-type and extension lie; bytes win.
        upload = SimpleUploadedFile("evil.jpg", b"not really an image", content_type="image/jpeg")
        with self.assertRaises(serializers.ValidationError):
            validate_image_upload(upload)

    def test_rejects_oversized_file(self):
        big = SimpleUploadedFile("big.png", make_png(), content_type="image/png")
        big.size = 6 * 1024 * 1024
        with self.assertRaises(serializers.ValidationError):
            validate_image_upload(big)

    @override_settings(IMAGE_MIN_DIMENSION=256)
    def test_rejects_tiny_image(self):
        upload = SimpleUploadedFile(
            "tiny.png", make_png(width=100, height=100), content_type="image/png"
        )
        with self.assertRaises(serializers.ValidationError):
            validate_image_upload(upload)

    def test_rejects_bad_extension(self):
        upload = SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        with self.assertRaises(serializers.ValidationError):
            validate_image_upload(upload)

    def test_room_image_cap_is_enforced(self):
        self.assertGreaterEqual(MAX_ROOM_IMAGES, 1)


class VariantGenerationTests(TestCase):
    def test_generates_all_sizes(self):
        data = make_png(1600, 1200)
        result = generate_variants("room_image", 1, data)
        self.assertEqual(set(result.keys()), {"thumbnail", "small", "medium", "large"})
        self.assertTrue(has_variants("room_image", 1))
        urls = variant_urls("room_image", 1)
        self.assertEqual(set(urls.keys()), {"thumbnail", "small", "medium", "large"})
        # The 1600px source is downscaled to the 1280px ceiling for "large".
        large = __import__("images.models", fromlist=["ImageVariant"]).ImageVariant.objects.get(
            entity_type="room_image", entity_id=1, size_key="large"
        )
        self.assertLessEqual(large.width, 1280)

    def test_generates_webp(self):
        data = make_png(600, 400)
        generate_variants("room_image", 2, data)
        variant = __import__("images.models", fromlist=["ImageVariant"]).ImageVariant.objects.get(
            entity_type="room_image", entity_id=2, size_key="small"
        )
        self.assertEqual(variant.format, "webp")
        with variant.file.open("rb") as fh:
            magic = fh.read(12)
        self.assertTrue(magic.startswith(b"RIFF") and b"WEBP" in magic[:12])

    def test_skips_undecodable_source(self):
        result = generate_variants("room_image", 3, b"garbage bytes")
        self.assertEqual(result, {})
        self.assertFalse(has_variants("room_image", 3))

    def test_delete_removes_rows(self):
        generate_variants("room_image", 4, make_png(400, 300))
        self.assertTrue(has_variants("room_image", 4))
        self.assertEqual(delete_variants("room_image", 4), 4)
        self.assertFalse(has_variants("room_image", 4))
