"""Tests for the automated KYC provider (Tier 4).

Properties under test:

- Off by default: with ``KYC_AUTO_APPROVE_ENABLED=False`` (the shipped
  default) a submission stays PENDING even when a provider is configured.
- Hard gates: an unreadable or reused document can never auto-approve.
- A clean, high-scoring document auto-approves when enabled, sets the
  tenant_verified flag and writes an audited ``tenant_kyc.auto_approved``
  event.
- The confidence bar is enforced.
"""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from users.kyc_provider import run_provider
from users.models import TenantVerification

User = get_user_model()


def _doc_image(kind="circle", size=(800, 500)) -> bytes:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    if kind == "circle":
        draw.ellipse((100, 100, 400, 350), fill=(60, 90, 180))
        draw.rectangle((450, 120, 700, 300), fill=(200, 200, 200))
    else:
        for x in range(0, size[0], 60):
            draw.line((x, 0, x, size[1]), fill=(30, 120, 90), width=8)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
        first_name="Rahim",
        phone="01712345678",
        date_of_birth="1995-05-10",
    )


def _submit(user, data: bytes):
    verification, _ = TenantVerification.objects.get_or_create(user=user)
    verification.doc_type = "nid"
    verification.file = SimpleUploadedFile("nid.jpg", data, content_type="image/jpeg")
    verification.status = TenantVerification.Status.PENDING
    verification.save()
    return verification


class ProviderUnitTests(TestCase):
    def test_provider_off_by_default(self):
        user = _make_user("kp_off")
        verification = _submit(user, _doc_image())
        self.assertIsNone(run_provider(verification))

    @override_settings(KYC_AUTO_APPROVE_ENABLED=True, KYC_PROVIDER="rules")
    def test_clean_document_auto_approves(self):
        user = _make_user("kp_clean")
        verification = _submit(user, _doc_image())
        result = run_provider(verification)
        self.assertIsNotNone(result)
        self.assertTrue(result.approved)
        self.assertGreaterEqual(result.confidence, 0.7)

    @override_settings(KYC_AUTO_APPROVE_ENABLED=True, KYC_PROVIDER="rules")
    def test_unreadable_document_never_approves(self):
        user = _make_user("kp_bad")
        verification = _submit(user, b"not an image at all")
        result = run_provider(verification)
        self.assertIsNotNone(result)
        self.assertFalse(result.approved)

    def test_unknown_provider_returns_none(self):
        with override_settings(KYC_AUTO_APPROVE_ENABLED=True, KYC_PROVIDER="madeup"):
            user = _make_user("kp_unk")
            verification = _submit(user, _doc_image())
            self.assertIsNone(run_provider(verification))


class AutoApproveWiringTests(APITestCase):
    def test_disabled_keeps_pending(self):
        user = _make_user("kp_wire_off")
        self.client.force_authenticate(user)
        resp = self.client.post(
            "/api/v1/users/tenant-kyc/",
            {"doc_type": "nid", "file": SimpleUploadedFile("nid.jpg", _doc_image(), "image/jpeg")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], TenantVerification.Status.PENDING)
        user.refresh_from_db()
        self.assertFalse(user.tenant_verified)

    @override_settings(KYC_AUTO_APPROVE_ENABLED=True, KYC_PROVIDER="rules")
    def test_enabled_auto_approves_and_audits(self):
        user = _make_user("kp_wire_on")
        self.client.force_authenticate(user)
        resp = self.client.post(
            "/api/v1/users/tenant-kyc/",
            {"doc_type": "nid", "file": SimpleUploadedFile("nid.jpg", _doc_image(), "image/jpeg")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], TenantVerification.Status.VERIFIED)
        user.refresh_from_db()
        self.assertTrue(user.tenant_verified)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="tenant_kyc.auto_approved", target_id=str(user.pk)
            ).exists()
        )
