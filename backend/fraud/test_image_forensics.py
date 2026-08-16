"""Tests for the photo-forensics layer (Tier 2).

Covers the forensics pipeline itself (ELA paste detection, watermark band,
editor EXIF, tiny/low-quality files) and its integration into the fraud
scan via the MANIPULATED_IMAGE detector.
"""

import io
import os
import random
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from fraud.models import FraudReport, FraudSignal
from fraud.services.detectors import run_scan
from fraud.services.image_forensics import analyze_image
from rooms.models import Room, RoomImage

User = get_user_model()


def _noise_photo(w=800, h=600, seed=11) -> Image.Image:
    """Photo-like noise: every pixel varies slightly around a row base —
    realistic enough that a single-generation JPEG has uniform ELA."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        base = rnd.randint(40, 200)
        for x in range(w):
            v = max(0, min(255, base + rnd.randint(-30, 30)))
            px[x, y] = (
                v,
                max(0, min(255, v + rnd.randint(-10, 10))),
                max(0, min(255, v - rnd.randint(0, 20))),
            )
    return img


def _jpeg_bytes(img: Image.Image, quality: int = 100) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _attack_bytes() -> bytes:
    """The classic paste attack: cut a region from a heavy re-encode (q55),
    paste it into the q100 original, save at q100. The pasted region carries
    a different compression generation → block-ELA inconsistency."""
    base = _noise_photo()
    lowgen = Image.open(io.BytesIO(_jpeg_bytes(base, quality=55)))
    composite = base.copy()
    composite.paste(lowgen.crop((0, 0, 320, 240)), (0, 0))
    return _jpeg_bytes(composite, quality=100)


def _watermark_bytes() -> bytes:
    """Textured body + a flat, uniform band along the bottom (watermark bar)."""
    img = Image.new("RGB", (800, 600))
    for y in range(540):
        for x in range(800):
            img.putpixel((x, y), ((x + y) % 255, (x * 2) % 255, (y * 3) % 255))
    for y in range(540, 600):
        for x in range(800):
            img.putpixel((x, y), (200, 200, 200))
    return _jpeg_bytes(img, quality=95)


def _editor_exif_bytes() -> bytes:
    img = _noise_photo()
    exif = Image.Exif()
    exif[305] = "Adobe Photoshop 24.0"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=100, exif=exif)
    return buf.getvalue()


def _make_user(username="forensics_owner") -> User:
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="test12345"
    )


def _make_room(owner, image_bytes: bytes, filename="photo.jpg") -> Room:
    room = Room.objects.create(
        owner=owner,
        title="Forensics Room",
        description="A unique description for the forensics listing.",
        room_type="single",
        price=9000,
        area="Mirpur",
        address="12 Road",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi"],
        size_sqft=250,
    )
    f = SimpleUploadedFile(filename, image_bytes, content_type="image/jpeg")
    RoomImage.objects.create(room=room, image=f, is_primary=True)
    return room


class ImageForensicsUnitTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, data: bytes, name: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_clean_photo_has_no_signals(self):
        result = analyze_image(self._write(_jpeg_bytes(_noise_photo()), "clean.jpg"))
        self.assertTrue(result.parsed)
        self.assertEqual(result.signals, [])

    def test_paste_attack_flagged_ela_tamper(self):
        result = analyze_image(self._write(_attack_bytes(), "attack.jpg"))
        self.assertTrue(
            any(s.key == "ela_tamper" and s.severity == "medium" for s in result.signals)
        )

    def test_heavy_recompression_alone_not_flagged(self):
        # Legit double-save (e.g. a screenshot of a photo) must NOT trigger.
        result = analyze_image(self._write(_jpeg_bytes(_noise_photo(), quality=60), "resave.jpg"))
        self.assertFalse(any(s.key == "ela_tamper" for s in result.signals))

    def test_tiny_image_flagged(self):
        tiny = Image.new("RGB", (200, 150), (120, 120, 120))
        result = analyze_image(self._write(_jpeg_bytes(tiny), "tiny.jpg"))
        self.assertTrue(any(s.key == "tiny_image" for s in result.signals))

    def test_watermark_band_flagged(self):
        result = analyze_image(self._write(_watermark_bytes(), "wm.jpg"))
        self.assertTrue(any(s.key == "watermark_overlay" for s in result.signals))

    def test_editor_exif_flagged(self):
        result = analyze_image(self._write(_editor_exif_bytes(), "edited.jpg"))
        self.assertTrue(any(s.key == "editor_software" for s in result.signals))

    def test_missing_file_parses_empty(self):
        result = analyze_image(os.path.join(self.tmp, "nope.jpg"))
        self.assertFalse(result.parsed)
        self.assertEqual(result.signals, [])


class ImageForensicsDetectorTests(TestCase):
    def setUp(self):
        self.owner = _make_user()

    def test_run_scan_flags_manipulated_image(self):
        room = _make_room(self.owner, _attack_bytes())
        report = run_scan(room)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.MANIPULATED_IMAGE, detectors)
        signal = report.signals.get(detector=FraudSignal.Detector.MANIPULATED_IMAGE)
        self.assertEqual(signal.severity, FraudReport.Severity.MEDIUM)
        self.assertTrue(signal.detail["images"])

    def test_run_scan_clean_photo_no_forensics_signal(self):
        room = _make_room(self.owner, _jpeg_bytes(_noise_photo()))
        report = run_scan(room)
        self.assertFalse(
            report.signals.filter(detector=FraudSignal.Detector.MANIPULATED_IMAGE).exists()
        )

    def test_run_scan_tolerates_missing_image_file(self):
        room = _make_room(self.owner, _jpeg_bytes(_noise_photo()))
        # Delete the file on disk — the detector must skip it, not crash.
        image = room.images.get()
        try:
            os.remove(image.image.path)
        except OSError:
            self.skipTest("could not delete image file")
        report = run_scan(room)
        self.assertFalse(
            report.signals.filter(detector=FraudSignal.Detector.MANIPULATED_IMAGE).exists()
        )
