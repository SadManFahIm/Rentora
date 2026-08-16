"""Tests for the automated KYC pre-screening (Tier 2)."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image, ImageDraw
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from users.kyc_auto import auto_screen
from users.models import TenantVerification

User = get_user_model()


def _doc_image(kind="circle", size=(800, 500)) -> bytes:
    """A structured, photo-like document image. Solid colours are avoided
    deliberately — they hash degenerate (all-zero pHash), which would make
    every solid-colour document look 'identical'."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    if kind == "circle":
        draw.ellipse((100, 100, 400, 350), fill=(60, 90, 180))
        draw.rectangle((450, 120, 700, 300), fill=(200, 200, 200))
    elif kind == "stripes":
        for y in range(0, size[1], 40):
            draw.rectangle((0, y, size[0], y + 22), fill=(140, 60, 40))
    elif kind == "grid":
        for x in range(0, size[0], 60):
            draw.line((x, 0, x, size[1]), fill=(30, 120, 90), width=8)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _make_user(username, phone="01712345678", dob="1995-05-10", first="Rahim"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
        first_name=first,
        phone=phone,
        date_of_birth=dob if dob else None,
    )


def _submit(user, data: bytes, name="nid.jpg", content_type="image/jpeg"):
    verification, _ = TenantVerification.objects.get_or_create(user=user)
    verification.doc_type = "nid"
    verification.file = SimpleUploadedFile(name, data, content_type=content_type)
    verification.status = TenantVerification.Status.PENDING
    verification.review_note = ""
    verification.reviewed_at = None
    verification.expires_at = None
    verification.save()
    return verification


def _log_rejection(user, admin):
    """Append an audit entry as the admin who rejected ``user``."""
    return AuditLogEntry.objects.create(
        actor=admin, action="tenant_kyc.rejected", target_id=str(user.pk), detail={"note": "x"}
    )


class AutoScreenUnitTests(TestCase):
    def test_valid_document_recommends_approve(self):
        user = _make_user("kyc_ok")
        verification = _submit(user, _doc_image())
        result = auto_screen(verification)
        self.assertEqual(result["result"], "recommend_approve")
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["reasons"], [])

    def test_duplicate_document_across_accounts_flagged(self):
        user_a = _make_user("kyc_dup_a")
        user_b = _make_user("kyc_dup_b")
        _submit(user_a, _doc_image("circle"))
        verification_b = _submit(user_b, _doc_image("circle"))
        result = auto_screen(verification_b)
        self.assertEqual(result["result"], "recommend_review")
        self.assertTrue(any("matches another account" in r for r in result["reasons"]))
        self.assertLess(result["score"], 70)

    def test_distinct_documents_not_flagged(self):
        user_a = _make_user("kyc_dist_a")
        user_b = _make_user("kyc_dist_b")
        _submit(user_a, _doc_image("circle"))
        verification_b = _submit(user_b, _doc_image("stripes"))
        result = auto_screen(verification_b)
        self.assertEqual(result["result"], "recommend_approve")

    def test_unreadable_file_flagged(self):
        user = _make_user("kyc_bad")
        # A .jpg that is actually plain text — passes the content-type gate,
        # fails the parse check.
        verification = _submit(user, b"this is not an image at all", name="fake.jpg")
        result = auto_screen(verification)
        self.assertEqual(result["result"], "recommend_review")
        self.assertTrue(any("not a readable image" in r for r in result["reasons"]))

    def test_tiny_document_flagged(self):
        user = _make_user("kyc_tiny")
        verification = _submit(user, _doc_image(size=(120, 90)))
        result = auto_screen(verification)
        self.assertEqual(result["result"], "recommend_review")
        self.assertTrue(any("screenshot or crop" in r for r in result["reasons"]))

    def test_incomplete_profile_reduces_score(self):
        user = _make_user("kyc_noprofile", phone="", dob=None, first="")
        verification = _submit(user, _doc_image())
        result = auto_screen(verification)
        # 100 - 10 (incomplete profile) = 90 — still recommend_approve, but
        # the penalty is visible in the score and reasons.
        self.assertEqual(result["score"], 90)
        self.assertTrue(any("missing phone/date-of-birth/name" in r for r in result["reasons"]))

    def test_repeat_rejections_penalty(self):
        admin = _make_user("kyc_admin_repeat")
        user = _make_user("kyc_repeat")
        _log_rejection(user, admin)
        _log_rejection(user, admin)
        verification = _submit(user, _doc_image())
        result = auto_screen(verification)
        self.assertEqual(result["score"], 90)
        self.assertTrue(any("prior unsuccessful" in r for r in result["reasons"]))

    def test_pdf_document_accepted(self):
        user = _make_user("kyc_pdf")
        pdf = b"%PDF-1.4\n% minimal fake pdf bytes for the parse check\n%%EOF"
        verification = _submit(user, pdf, name="scan.pdf", content_type="application/pdf")
        result = auto_screen(verification)
        self.assertEqual(result["result"], "recommend_approve")


class AutoScreenApiTests(APITestCase):
    def setUp(self):
        self.user = _make_user("kyc_api")
        self.client.force_authenticate(self.user)
        self.url = reverse("tenant-kyc")

    def test_submit_runs_auto_screen_and_exposes_it(self):
        response = self.client.post(
            self.url,
            {
                "doc_type": "nid",
                "file": SimpleUploadedFile("doc.jpg", _doc_image(), content_type="image/jpeg"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["auto_screen_result"], "recommend_approve")
        self.assertGreaterEqual(response.data["auto_screen_score"], 70)
        self.assertIn("reasons", response.data["auto_screen_detail"])

    def test_admin_queue_includes_recommendation(self):
        admin = _make_user("kyc_admin", first="Admin")
        admin.role = "admin"
        admin.is_staff = True
        admin.save()

        bad_tenant = _make_user("kyc_badtenant")
        self.client.force_authenticate(bad_tenant)
        self.client.post(
            self.url,
            {
                "doc_type": "nid",
                "file": SimpleUploadedFile(
                    "tiny.jpg", _doc_image(size=(80, 60)), content_type="image/jpeg"
                ),
            },
            format="multipart",
        )

        self.client.force_authenticate(admin)
        queue = self.client.get(reverse("tenant-kyc-pending")).data
        entry = next(u for u in queue if u["username"] == "kyc_badtenant")
        verification = entry["verification"]
        self.assertEqual(verification["auto_screen_result"], "recommend_review")
        self.assertTrue(
            any("screenshot or crop" in r for r in verification["auto_screen_detail"]["reasons"])
        )
