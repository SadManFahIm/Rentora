"""Tests for the optional ClamAV scan (Tier 2) and the upload integration.

No real clamd daemon is needed — the network socket client is mocked at the
``chat.antivirus._clamd_client`` seam and the view integration patches
``chat.views.scan_bytes``.
"""

import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from chat import antivirus
from chat.antivirus import scan_bytes

User = get_user_model()


class _FakeClamd:
    """Stands in for pyclamd's network socket client."""

    def __init__(self, result=None):
        self._result = result

    def ping(self):
        return "PONG"

    def instream(self, stream):
        # instream expects a readable stream; our seam passes BytesIO.
        stream.read()
        return self._result


class ScanBytesTests(TestCase):
    def test_disabled_returns_unavailable_clean(self):
        with override_settings(CLAMAV_ENABLED=False):
            result = scan_bytes(b"hello")
        self.assertFalse(result.available)
        self.assertTrue(result.clean)
        self.assertFalse(result.rejected)

    def test_clean_file_when_clamd_answers(self):
        with (
            override_settings(CLAMAV_ENABLED=True),
            mock.patch.object(antivirus, "_clamd_client", return_value=_FakeClamd(result=None)),
        ):
            result = scan_bytes(b"clean content")
        self.assertTrue(result.available)
        self.assertTrue(result.clean)

    def test_infected_file_rejected(self):
        with (
            override_settings(CLAMAV_ENABLED=True),
            mock.patch.object(
                antivirus,
                "_clamd_client",
                return_value=_FakeClamd(result={"stream": "Eicar-Test-Signature"}),
            ),
        ):
            result = scan_bytes(
                b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
            )
        self.assertTrue(result.available)
        self.assertFalse(result.clean)
        self.assertTrue(result.rejected)
        self.assertIn("Eicar-Test-Signature", result.viruses)

    def test_unreachable_daemon_falls_back_clean(self):
        with (
            override_settings(CLAMAV_ENABLED=True),
            mock.patch.object(antivirus, "_clamd_client", return_value=None),
        ):
            result = scan_bytes(b"whatever")
        self.assertFalse(result.available)
        self.assertTrue(result.clean)
        self.assertFalse(result.rejected)

    def test_scan_exception_falls_back_clean(self):
        with (
            override_settings(CLAMAV_ENABLED=True),
            mock.patch.object(antivirus, "_clamd_client", return_value=_FakeClamd(result=None)),
            mock.patch.object(_FakeClamd, "instream", side_effect=Exception("socket error")),
        ):
            result = scan_bytes(b"content")
        self.assertFalse(result.available)
        self.assertTrue(result.clean)


class UploadIntegrationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="upload_scanner",
            email="upload_scanner@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("chat-upload")

    def _png_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(buf, "PNG")
        return SimpleUploadedFile("photo.png", buf.getvalue(), content_type="image/png")

    def test_upload_rejected_when_infected(self):
        with mock.patch(
            "chat.views.scan_bytes",
            return_value=antivirus.ScanResult(available=True, clean=False, viruses=["Eicar"]),
        ):
            response = self.client.post(self.url, {"file": self._png_file()}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("security scan", response.data["detail"])

    def test_upload_accepted_when_clean(self):
        with mock.patch(
            "chat.views.scan_bytes",
            return_value=antivirus.ScanResult(available=True, clean=True),
        ):
            response = self.client.post(self.url, {"file": self._png_file()}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message_type"], "image")

    def test_upload_accepted_when_scanner_unavailable(self):
        # No scanner → clean-by-default; the upload must still work.
        with mock.patch(
            "chat.views.scan_bytes",
            return_value=antivirus.ScanResult(available=False, clean=True),
        ):
            response = self.client.post(self.url, {"file": self._png_file()}, format="multipart")
        self.assertEqual(response.status_code, 201)
