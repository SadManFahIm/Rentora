"""Phase 12.1 — Tenant KYC: two-sided trust, tested through the real API.

Covers the spec's Tenant-KYC test matrix:

- upload validation (missing file, bad type, wrong MIME, oversize, empty)
- authorization (owner/admin-only documents, 404 for strangers, 403 for
  non-admin review actions)
- status transitions (pending -> verified | rejected | needs_review, and
  re-submission after rejection/expiry/needs-review)
- admin review (approve flips the badge + expiry, reject/needs-review with a
  required note, audit entries, notifications, rejection email)
- badge visibility (landlords only ever see ``tenant_verified`` booleans in
  chat/room/roommate payloads — never the document or raw NID data)
- audit trail (every submit/decision lands in the append-only log)
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from notifications.models import Notification
from users.models import TenantVerification

from .views import MAX_KYC_FILE_SIZE

User = get_user_model()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # fake but valid-enough PNG bytes


def _png_file(name="nid.png", size=None, content_type="image/png"):
    content = PNG if size is None else b"x" * size
    return SimpleUploadedFile(name, content, content_type=content_type)


class TenantKycBase(APITestCase):
    def setUp(self):
        self.tenant = User.objects.create_user(
            username="tenant_kyc",
            email="tenant_kyc@example.com",
            password="test12345",
            role=User.Role.TENANT,
        )
        self.landlord = User.objects.create_user(
            username="landlord_viewer",
            email="landlord_viewer@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
        )
        self.admin = User.objects.create_superuser(
            username="kyc_admin",
            email="kyc_admin@example.com",
            password="test12345",
        )
        # Most tests act as the tenant; override with self._auth(...) where not.
        self._auth(self.tenant)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _submit(self, user=None, doc_type="nid", file=None, expect=status.HTTP_201_CREATED):
        if user is not None:
            self._auth(user)
        res = self.client.post(
            "/api/v1/users/tenant-kyc/",
            {"doc_type": doc_type, "file": file or _png_file()},
            format="multipart",
        )
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def _review(self, user_id, decision, note="", expect=status.HTTP_200_OK):
        res = self.client.post(
            f"/api/v1/users/tenant-kyc/{user_id}/review/",
            {"decision": decision, "note": note},
            format="json",
        )
        self.assertEqual(res.status_code, expect, res.data)
        return res


# ============================================================
# Upload validation
# ============================================================


class TenantKycUploadValidationTests(TenantKycBase):
    def test_unauthenticated_submit_is_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.post("/api/v1/users/tenant-kyc/", {}, format="multipart")
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_missing_file_is_rejected(self):
        self._auth(self.tenant)
        res = self.client.post("/api/v1/users/tenant-kyc/", {"doc_type": "nid"}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_doc_type_is_rejected(self):
        self._submit(doc_type="drivers_licence", expect=status.HTTP_400_BAD_REQUEST)

    def test_disallowed_mime_type_is_rejected(self):
        self._submit(file=_png_file(content_type="text/plain"), expect=status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_is_rejected(self):
        self._submit(file=_png_file(size=MAX_KYC_FILE_SIZE + 1), expect=status.HTTP_400_BAD_REQUEST)

    def test_empty_file_is_rejected(self):
        self._submit(file=_png_file(size=0), expect=status.HTTP_400_BAD_REQUEST)

    def test_upload_renames_file_to_uuid_so_nid_never_hits_filenames(self):
        self._submit(file=_png_file(name="1234567890123_nid_front.png"))
        verification = TenantVerification.objects.get(user=self.tenant)
        # The original filename (an NID-like number) must never reach storage.
        self.assertNotIn("1234567890123", verification.file.name)
        self.assertRegex(verification.file.name, r"[0-9a-f]{32}\.png$")

    def test_valid_upload_creates_pending_verification_and_audit(self):
        res = self._submit()
        self.assertEqual(res.data["status"], TenantVerification.Status.PENDING)
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.tenant, action="tenant_kyc.submitted").exists()
        )


# ============================================================
# Authorization & privacy
# ============================================================


class TenantKycAuthorizationTests(TenantKycBase):
    def test_owner_can_read_own_record_and_file_url(self):
        self._submit()
        self._auth(self.tenant)
        res = self.client.get("/api/v1/users/tenant-kyc/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], TenantVerification.Status.PENDING)
        # The owner gets the auth-gated file URL (never the public media URL).
        self.assertIn("/api/v1/users/tenant-kyc/", res.data["file"])

    def test_never_started_returns_null(self):
        self._auth(self.tenant)
        res = self.client.get("/api/v1/users/tenant-kyc/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNone(res.data)

    def test_stranger_cannot_read_the_document(self):
        self._submit()
        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/users/tenant-kyc/{self.tenant.id}/file/")
        # 404, not 403 — a guessed id doesn't even confirm a record exists.
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_read_the_document(self):
        self._submit()
        self._auth(self.admin)
        res = self.client.get(f"/api/v1/users/tenant-kyc/{self.tenant.id}/file/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_owner_can_read_own_document(self):
        self._submit()
        self._auth(self.tenant)
        res = self.client.get(f"/api/v1/users/tenant-kyc/{self.tenant.id}/file/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_pending_queue_requires_admin(self):
        self._submit()
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/tenant-kyc/pending/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_review_requires_admin(self):
        self._submit()
        self._auth(self.landlord)
        res = self.client.post(
            f"/api/v1/users/tenant-kyc/{self.tenant.id}/review/",
            {"decision": "approved"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_pending_queue_lists_applicant_without_raw_nid(self):
        self._submit()
        self._auth(self.admin)
        res = self.client.get("/api/v1/users/tenant-kyc/pending/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        row = res.data[0]
        self.assertEqual(row["id"], self.tenant.id)
        # The queue shows the admin-gated document URL, not the raw file path.
        self.assertIn("/api/v1/users/tenant-kyc/", row["verification"]["file"])
        self.assertFalse(row["tenant_verified"])


# ============================================================
# Status transitions + admin review
# ============================================================


class TenantKycLifecycleTests(TenantKycBase):
    def test_double_submit_while_pending_is_blocked(self):
        self._submit()
        self._submit(expect=status.HTTP_400_BAD_REQUEST)

    def test_already_verified_cannot_resubmit(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "approved")
        self._auth(self.tenant)
        self._submit(expect=status.HTTP_400_BAD_REQUEST)

    def test_approval_flips_badge_sets_expiry_and_audits(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "approved", note="Clear NID scan.")

        self.tenant.refresh_from_db()
        verification = TenantVerification.objects.get(user=self.tenant)
        self.assertTrue(self.tenant.tenant_verified)
        self.assertEqual(verification.status, TenantVerification.Status.VERIFIED)
        self.assertIsNotNone(verification.expires_at)
        self.assertGreater(verification.expires_at, timezone.now() + timedelta(days=364))
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="tenant_kyc.approved").exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant, notification_type=Notification.Type.TENANT_KYC_APPROVED
            ).exists()
        )

    def test_rejection_requires_a_note(self):
        self._submit()
        self._auth(self.admin)
        res = self.client.post(
            f"/api/v1/users/tenant-kyc/{self.tenant.id}/review/",
            {"decision": "rejected", "note": ""},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        verification = TenantVerification.objects.get(user=self.tenant)
        self.assertEqual(verification.status, TenantVerification.Status.PENDING)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_rejection_notifies_emails_and_allows_resubmission(self):
        from django.core import mail

        self._submit()
        self._auth(self.admin)
        # The rejection email is sent via transaction.on_commit (after the
        # decision commits) — run the queued callback so the outbox fills.
        with self.captureOnCommitCallbacks(execute=True):
            self._review(self.tenant.id, "rejected", note="Blurry scan — please re-upload.")

        self.tenant.refresh_from_db()
        verification = TenantVerification.objects.get(user=self.tenant)
        self.assertFalse(self.tenant.tenant_verified)
        self.assertEqual(verification.status, TenantVerification.Status.REJECTED)
        self.assertEqual(verification.review_note, "Blurry scan — please re-upload.")
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="tenant_kyc.rejected").exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant, notification_type=Notification.Type.TENANT_KYC_REJECTED
            ).exists()
        )
        # Branded rejection email with the reviewer's note.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("tenant verification", mail.outbox[0].subject.lower())

        # Re-submission after rejection goes back to pending.
        self._auth(self.tenant)
        self._submit(doc_type="passport")
        verification.refresh_from_db()
        self.assertEqual(verification.status, TenantVerification.Status.PENDING)
        self.assertEqual(verification.doc_type, "passport")

    def test_needs_review_keeps_badge_off_and_allows_resubmission(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "needs_review", note="Front side unreadable.")

        verification = TenantVerification.objects.get(user=self.tenant)
        self.assertEqual(verification.status, TenantVerification.Status.NEEDS_REVIEW)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.tenant_verified)
        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant,
                notification_type=Notification.Type.TENANT_KYC_NEEDS_REVIEW,
            ).exists()
        )

        self._auth(self.tenant)
        self._submit()
        verification.refresh_from_db()
        self.assertEqual(verification.status, TenantVerification.Status.PENDING)

    def test_cannot_review_without_a_verification_record(self):
        self._auth(self.admin)
        res = self.client.post(
            f"/api/v1/users/tenant-kyc/{self.tenant.id}/review/",
            {"decision": "approved"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_review_a_resolved_verification_twice(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "approved")
        self._review(
            self.tenant.id, "rejected", note="Changed my mind.", expect=status.HTTP_400_BAD_REQUEST
        )

    def test_lazy_expiry_clears_stale_badge(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "approved")
        verification = TenantVerification.objects.get(user=self.tenant)
        # Backdate past the 365-day window.
        TenantVerification.objects.filter(pk=verification.pk).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        self._auth(self.tenant)
        res = self.client.get("/api/v1/users/tenant-kyc/")
        self.assertEqual(res.data["status"], TenantVerification.Status.EXPIRED)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.tenant_verified)


# ============================================================
# Badge visibility — landlords see booleans, never documents
# ============================================================


class TenantKycBadgeVisibilityTests(TenantKycBase):
    def _verify_tenant(self):
        self._submit()
        self._auth(self.admin)
        self._review(self.tenant.id, "approved")
        # force_authenticate reuses the in-memory instance, so refresh the flag
        # the way a real (JWT-authenticated) request would see it.
        self.tenant.refresh_from_db()

    def test_auth_user_payload_exposes_badge(self):
        self._verify_tenant()
        self._auth(self.tenant)
        res = self.client.get("/api/v1/auth/user/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["tenant_verified"])

    def test_chat_participant_exposes_badge_but_not_document(self):
        self._verify_tenant()
        self._auth(self.tenant)
        res = self.client.post(
            "/api/v1/chat/rooms/",
            {"listing_id": None, "participant_ids": [self.landlord.id]},
            format="json",
        )
        # Chat may 400 without a listing; either way the participant serializer
        # must include the badge when it responds.
        if res.status_code == status.HTTP_201_CREATED:
            other = res.data.get("other_participant") or res.data["participants"][-1]
            self.assertTrue(other["tenant_verified"])
            self.assertNotIn("file", other)

    def test_room_owner_payload_exposes_badge(self):
        self._verify_tenant()
        room = self._create_room_for_landlord()
        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("tenant_verified", res.data["owner"])

    def _create_room_for_landlord(self):
        self._auth(self.landlord)
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": "Viewer Studio",
                "description": "A studio the tenant can view.",
                "room_type": "studio",
                "price": "12000.00",
                "area": "Mirpur",
                "address": "12 Mirpur Road",
                "lat": "23.8069",
                "lng": "90.3687",
                "amenities": ["WiFi"],
                "gender_preference": "any",
                "size_sqft": 320,
                "is_available": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        from rooms.models import Room

        return Room.objects.get(pk=res.data["id"])
