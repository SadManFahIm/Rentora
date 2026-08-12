"""Security regression tests.

Covers the hardening layer added with the public-repo security audit:

  * file-upload validation (extension / content-type / size) on room images,
  * authorization gating on admin-only fraud endpoints (non-admin 403),
  * IDOR checks — a user cannot modify/delete another user's listing or
    review another user's fraud report, and KYC documents are owner/admin-only.

These are the automated half of the checks in docs/SECURITY_CHECKLIST.md; the
deployment half (DEBUG=False, HTTPS-only headers, restricted CORS) is enforced
by ``config/settings/prod.py`` and the CI security job.
"""

import base64

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from fraud.models import FraudReport
from rooms.models import Room
from users.models import KycDocument

User = get_user_model()

# A 1x1 transparent PNG — valid for Pillow, valid image upload.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        **kwargs,
    )


class RoomImageUploadSecurityTests(APITestCase):
    """uploaded_images must reject non-images and oversized files."""

    def setUp(self):
        self.owner = make_user("uploader")
        self.client.force_authenticate(self.owner)

    def _payload(self, files):
        return {
            "title": "Security Test Room",
            "description": "A room used by the security regression suite.",
            "room_type": "single",
            "price": "5000.00",
            "area": "Mirpur",
            "address": "House 1, Road 1, Mirpur 10",
            "lat": "23.806000",
            "lng": "90.368000",
            "size_sqft": 160,
            "uploaded_images": files,
        }

    def test_non_image_extension_rejected(self):
        evil = SimpleUploadedFile("payload.txt", b"<script>alert(1)</script>")
        resp = self.client.post("/api/v1/rooms/", self._payload([evil]), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # The unified error envelope carries a human-readable message.
        self.assertNotEqual(resp.data.get("message", ""), "")

    def test_oversized_image_rejected(self):
        big = SimpleUploadedFile(
            "big.png", _PNG + b"\x00" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        resp = self.client.post("/api/v1/rooms/", self._payload([big]), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotEqual(resp.data.get("message", ""), "")

    def test_valid_image_accepted(self):
        ok = SimpleUploadedFile("room.png", _PNG, content_type="image/png")
        resp = self.client.post("/api/v1/rooms/", self._payload([ok]), format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class AdminOnlyFraudTests(APITestCase):
    """Fraud summary/operations endpoints are admin-only (server-side)."""

    def setUp(self):
        self.user = make_user("normaluser")
        self.admin = make_user("fraudadmin", is_staff=True)
        self.owner = make_user("fraudowner")
        self.room = Room.objects.create(
            owner=self.owner,
            title="Fraud Security Room",
            description="A room for the security suite.",
            room_type="single",
            price="6000.00",
            area="Mirpur",
            address="House 2, Road 2, Mirpur 10",
            lat="23.806000",
            lng="90.368000",
            size_sqft=160,
        )

    def test_summary_requires_admin(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/fraud/summary/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_summary_allowed_for_admin(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/v1/fraud/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("total", resp.data)

    def test_non_admin_cannot_review_report(self):
        # The fraud auto-scan signal already created a report for the room;
        # update it to a pending state instead of creating a duplicate.
        report, _ = FraudReport.objects.update_or_create(
            room=self.room, defaults={"score": 60, "status": FraudReport.Status.OPEN}
        )
        self.client.force_authenticate(self.user)
        resp = self.client.post(f"/api/v1/fraud/reports/{report.id}/review/", {"status": "cleared"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class IdorTests(APITestCase):
    """Cross-user resource access must fail server-side."""

    def setUp(self):
        self.user_a = make_user("user_a")
        self.user_b = make_user("user_b")
        self.room_b = Room.objects.create(
            owner=self.user_b,
            title="User B's Room",
            description="Private room.",
            room_type="single",
            price="5500.00",
            area="Uttara",
            address="House 3, Road 3, Uttara Sector 4",
            lat="23.875000",
            lng="90.379000",
            size_sqft=150,
        )

    def test_cannot_delete_another_users_room(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.delete(f"/api/v1/rooms/{self.room_b.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_update_another_users_room(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.patch(
            f"/api/v1/rooms/{self.room_b.id}/", {"price": "9999.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_kyc_document_is_owner_or_admin_only(self):
        self.user_b.nid_verified = True
        self.user_b.save()
        doc = KycDocument.objects.create(
            user=self.user_b,
            doc_type=KycDocument.DocType.NID,
            file=SimpleUploadedFile("nid.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
        )
        # A stranger must not be able to fetch the document (404 on purpose —
        # a guessed id must not confirm a document exists).
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(f"/api/v1/users/kyc/documents/{doc.id}/file/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # The owner can.
        self.client.force_authenticate(self.user_b)
        resp = self.client.get(f"/api/v1/users/kyc/documents/{doc.id}/file/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_302_FOUND))
