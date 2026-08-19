"""Phase 15 (C4) — AI NID OCR auto-extract tests.

Covers the pure NID-text parser (17/13-digit numbers, name/DOB extraction,
confidence levels), the provider-based OCR step (none/http + graceful
failure), and the auto_screen integration (score boost + OCR detail stored
in the admin-facing pre-screen output).
"""

import io
import os
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from .kyc_auto import auto_screen
from .kyc_ocr import extract_ocr_text, ocr_score_boost, ocr_screen, parse_nid_text
from .models import TenantVerification

User = get_user_model()


def _png_bytes(size=(600, 400)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def _make_verification(user, content=b"", name="nid.png"):
    verification = TenantVerification.objects.create(
        user=user, status=TenantVerification.Status.PENDING
    )
    if content:
        verification.file = SimpleUploadedFile(name, content, content_type="image/png")
        verification.save()
    return verification


class ParseNidTextTests(APITestCase):
    def test_17_digit_number(self):
        parsed = parse_nid_text("National ID: 12345678901234567")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["nid_number"], "12345678901234567")
        self.assertEqual(parsed["confidence"], "low")

    def test_13_digit_legacy_number(self):
        parsed = parse_nid_text("ID 1234567890123")
        self.assertEqual(parsed["nid_number"], "1234567890123")

    def test_full_document_extracts_name_and_dob(self):
        text = (
            "Government of Bangladesh\n"
            "Name: FAHIM RAHMAN\n"
            "Date of Birth: 15/08/1995\n"
            "National ID No: 12345678901234567\n"
        )
        parsed = parse_nid_text(text)
        self.assertEqual(parsed["nid_number"], "12345678901234567")
        self.assertIn("FAHIM", parsed["name"])
        self.assertEqual(parsed["date_of_birth"], "15/08/1995")
        self.assertEqual(parsed["confidence"], "high")

    def test_invalid_date_is_rejected(self):
        parsed = parse_nid_text("DOB 45/13/1990\n12345678901234567")
        self.assertEqual(parsed["date_of_birth"], None)
        # No valid DOB and no name line survived -> number-only confidence.
        self.assertEqual(parsed["confidence"], "low")

    def test_garbage_is_none(self):
        self.assertIsNone(parse_nid_text("just some random text"))
        self.assertIsNone(parse_nid_text(""))
        self.assertIsNone(parse_nid_text(None))

    def test_name_line_requires_caps_or_bangla(self):
        text = "this is lowercase words here\n12345678901234567"
        parsed = parse_nid_text(text)
        self.assertIsNone(parsed["name"])

    def test_bangla_name_extracted(self):
        text = "নাম: রহমান\n১২৩৪৫৬৭৮৯০১২৩৪৫৬৭\n"
        parsed = parse_nid_text(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["name"], "নাম: রহমান")
        self.assertEqual(parsed["nid_number"], "১২৩৪৫৬৭৮৯০১২৩৪৫৬৭")


class ExtractOcrTextTests(APITestCase):
    def test_none_provider_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nid.png")
            with open(path, "wb") as fh:
                fh.write(_png_bytes())
            with override_settings(KYC_OCR_PROVIDER="none"):
                self.assertIsNone(extract_ocr_text(path))

    def test_missing_file_returns_none(self):
        self.assertIsNone(extract_ocr_text("/nonexistent/nid.png"))

    def test_http_provider_success(self):
        fake = mock.Mock()
        fake.json.return_value = {"text": "National ID 12345678901234567"}
        fake.raise_for_status = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nid.png")
            with open(path, "wb") as fh:
                fh.write(_png_bytes())
            with (
                override_settings(
                    KYC_OCR_PROVIDER="http",
                    KYC_OCR_GATEWAY_URL="https://ocr.invalid/v1",
                ),
                mock.patch("requests.post", return_value=fake) as post,
            ):
                text = extract_ocr_text(path)
        self.assertEqual(text, "National ID 12345678901234567")
        post.assert_called_once()

    def test_http_provider_failure_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nid.png")
            with open(path, "wb") as fh:
                fh.write(_png_bytes())
            with (
                override_settings(
                    KYC_OCR_PROVIDER="http",
                    KYC_OCR_GATEWAY_URL="https://ocr.invalid/v1",
                ),
                mock.patch("requests.post", side_effect=RuntimeError("down")),
            ):
                self.assertIsNone(extract_ocr_text(path))

    def test_http_provider_without_url_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nid.png")
            with open(path, "wb") as fh:
                fh.write(_png_bytes())
            with override_settings(KYC_OCR_PROVIDER="http", KYC_OCR_GATEWAY_URL=""):
                self.assertIsNone(extract_ocr_text(path))


class OcrScreenTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ocr_user", email="ocr@example.com", password="test12345"
        )

    @override_settings(KYC_OCR_ENABLED=False)
    def test_disabled_screen(self):
        verification = _make_verification(self.user, _png_bytes())
        screen = ocr_screen(verification)
        self.assertFalse(screen["enabled"])
        self.assertIsNone(screen["extracted"])

    def test_enabled_but_no_provider(self):
        verification = _make_verification(self.user, _png_bytes())
        with override_settings(KYC_OCR_ENABLED=True, KYC_OCR_PROVIDER="none"):
            screen = ocr_screen(verification)
        self.assertTrue(screen["enabled"])
        self.assertIsNone(screen["extracted"])

    def test_pdf_skipped(self):
        verification = _make_verification(self.user, b"%PDF-1.4 fake", name="scan.pdf")
        with override_settings(KYC_OCR_ENABLED=True, KYC_OCR_PROVIDER="http"):
            screen = ocr_screen(verification)
        self.assertIn("PDF", screen["note"])
        self.assertIsNone(screen["extracted"])


class AutoScreenIntegrationTests(APITestCase):
    def _verified_user(self):
        return User.objects.create_user(
            username="kyc_ocr_user",
            email="kyc_ocr@example.com",
            password="test12345",
            phone="01712345678",
            first_name="Fahim",
            date_of_birth="1995-08-15",
        )

    def test_ocr_boost_applies_with_valid_nid(self):
        fake = mock.Mock()
        fake.json.return_value = {"text": "Name: FAHIM RAHMAN\nDOB 15/08/1995\n12345678901234567"}
        fake.raise_for_status = lambda: None
        with (
            override_settings(
                KYC_OCR_ENABLED=True,
                KYC_OCR_PROVIDER="http",
                KYC_OCR_GATEWAY_URL="https://ocr.invalid/v1",
            ),
            mock.patch("requests.post", return_value=fake),
        ):
            verification = _make_verification(self._verified_user(), _png_bytes())
            screen = auto_screen(verification)
        self.assertEqual(screen["score"], 100)
        self.assertEqual(screen["result"], "recommend_approve")
        self.assertIsNotNone(screen["ocr"])
        self.assertEqual(screen["ocr"]["nid_number"], "12345678901234567")
        self.assertIn("OCR", " ".join(screen["reasons"]))

    def test_ocr_disabled_does_not_boost(self):
        with override_settings(KYC_OCR_ENABLED=False):
            verification = _make_verification(self._verified_user(), _png_bytes())
            screen = auto_screen(verification)
        self.assertEqual(screen["score"], 100)
        self.assertIsNone(screen["ocr"])

    def test_ocr_score_boost_values(self):
        self.assertEqual(ocr_score_boost(None), 0)
        self.assertEqual(ocr_score_boost({"nid_number": ""}), 0)
        self.assertEqual(ocr_score_boost({"nid_number": "12345678901234567"}), 5)
