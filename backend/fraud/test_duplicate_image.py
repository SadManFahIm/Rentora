"""Tests for the cross-listing duplicate-image fraud detector (Phase 11).

Covers: same-image detection across listings, same-listing tolerance,
contextual severity (same owner = low, different owners = medium/high),
threshold behaviour, and the fraud-engine integration via ``run_scan``.
"""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw

from fraud.models import FraudReport, FraudSignal
from fraud.services.detectors import run_scan
from fraud.services.duplicate_image import duplicate_image_signal, find_duplicate_images
from rooms.models import Room, RoomImage, RoomImageHash

User = get_user_model()


def make_user(username, nid_verified=True):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        nid_verified=nid_verified,
    )


def _png(kind="circle") -> bytes:
    """A structured, photo-like image so the hash carries real signal.

    Two distinct kinds (circle vs stripes) hash differently; the same kind
    hashes identically — exactly the two cases the detector must tell apart.
    Solid-colour images are deliberately avoided: they hash degenerate.
    """
    img = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(img)
    if kind == "circle":
        draw.ellipse((12, 12, 52, 52), fill=(200, 60, 40))
    elif kind == "stripes":
        for y in range(0, 64, 8):
            draw.rectangle((0, y, 64, y + 4), fill=(40, 90, 200))
    else:  # rotated variant — should still match the circle closely
        draw.ellipse((14, 10, 54, 54), fill=(200, 60, 40))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def make_room(
    owner,
    title="Room",
    area="Mirpur",
    price=8000,
    png=None,
    attach_image=True,
    different_png=None,
):
    room = Room.objects.create(
        owner=owner,
        title=title,
        description="A short description that is unique enough.",
        room_type="single",
        price=price,
        area=area,
        address="12 Road",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi"],
        size_sqft=250,
    )
    if attach_image:
        f = SimpleUploadedFile(f"{room.pk}-photo.png", png or _png(), content_type="image/png")
        RoomImage.objects.create(room=room, image=f, is_primary=True)
    if different_png:
        f2 = SimpleUploadedFile(f"{room.pk}-photo2.png", different_png, content_type="image/png")
        RoomImage.objects.create(room=room, image=f2)
    return room


def _photo_bytes(seed: int) -> bytes:
    return _png(seed)


class DuplicateImageDetectorTests(TestCase):
    def setUp(self):
        self.owner_a = make_user("img_owner_a")
        self.owner_b = make_user("img_owner_b")
        self.png = _png("circle")
        # A genuinely different photo (stripes vs circle = different structure).
        self.other_png = _png("stripes")

    def test_same_image_different_listings_flagged(self):
        a = make_room(self.owner_a, "Listing A", png=self.png)
        b = make_room(self.owner_b, "Listing B", png=self.png)
        signal = duplicate_image_signal(b)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.detector, FraudSignal.Detector.DUPLICATE_IMAGE)
        self.assertEqual(signal.severity, FraudReport.Severity.MEDIUM)
        self.assertEqual(signal.detail["matched_listing_ids"], [a.pk])
        self.assertFalse(signal.detail["same_owner"])

    def test_different_owner_and_area_is_high(self):
        make_room(self.owner_a, "Listing A", area="Uttara", png=self.png)
        b = make_room(self.owner_b, "Listing B", area="Mirpur", png=self.png)
        signal = duplicate_image_signal(b)
        self.assertEqual(signal.severity, FraudReport.Severity.HIGH)

    def test_same_owner_is_low(self):
        make_room(self.owner_a, "Listing A", png=self.png)
        b = make_room(self.owner_a, "Listing B", png=self.png)
        signal = duplicate_image_signal(b)
        self.assertEqual(signal.severity, FraudReport.Severity.LOW)
        self.assertTrue(signal.detail["same_owner"])

    def test_distinct_images_clean(self):
        make_room(self.owner_a, "Listing A", png=self.png)
        b = make_room(self.owner_b, "Listing B", png=self.other_png)
        self.assertIsNone(duplicate_image_signal(b))

    def test_same_listing_duplicate_gallery_not_flagged(self):
        # Two photos in ONE listing are a gallery, not cross-listing fraud.
        b = make_room(self.owner_b, "Listing B", png=self.png, different_png=self.png)
        signal = duplicate_image_signal(b)
        self.assertIsNone(signal)

    def test_feature_flag_disables_detector(self):
        make_room(self.owner_a, "Listing A", png=self.png)
        b = make_room(self.owner_b, "Listing B", png=self.png)
        with override_settings(DUPLICATE_IMAGE_FRAUD_ENABLED=False):
            self.assertIsNone(duplicate_image_signal(b))

    def test_run_scan_integrates_duplicate_image_signal(self):
        a = make_room(self.owner_a, "Listing A", png=self.png)
        b = make_room(self.owner_b, "Listing B", png=self.png)
        report = run_scan(b)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.DUPLICATE_IMAGE, detectors)
        self.assertEqual(report.severity, FraudReport.Severity.HIGH)
        self.assertGreater(report.score, 0)
        self.assertTrue(
            any(s.detail.get("matched_listing_ids") == [a.pk] for s in report.signals.all())
        )

    def test_find_duplicate_images_dedupes_multiple_rooms(self):
        make_room(self.owner_a, "Listing A", png=self.png)
        make_room(self.owner_b, "Listing B", png=self.png)
        c = make_room(self.owner_b, "Listing C", png=self.png)
        matches = find_duplicate_images(c)
        self.assertEqual(len(matches), 2)

    def test_cache_warmed_for_previous_listing(self):
        # The detector must work even when the earlier listing's photo was
        # never hashed before (the warm-up pass hashes it on this scan).
        make_room(self.owner_a, "Listing A", png=self.png)
        self.assertEqual(RoomImageHash.objects.count(), 0)
        b = make_room(self.owner_b, "Listing B", png=self.png)
        signal = duplicate_image_signal(b)
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(RoomImageHash.objects.count(), 2)
