"""E2E: the KYC -> verified-badge trust chain, through the real API.

1. An unverified landlord publishes a room -> the listing reports
   ``verified=False`` and ``owner.nid_verified=False``, and the fraud
   auto-scan flags the "unverified owner" signal.
2. An admin approves the landlord's KYC (``nid_verified=True``) -> the users
   signal flips ``Room.verified`` on every one of the landlord's listings.
3. The listing API now carries the badge data and a re-scan drops the
   unverified-owner signal.
4. Revoking verification removes the badges again.
5. Roommate matching exposes the KYC state so verified users stand out.

The later half of this module drives the *admin review panel*: document
uploads (multipart), the pending queue, and approve/reject — all through
HTTP, the way the browser does.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from fraud.models import FraudReport, FraudSignal
from notifications.models import Notification
from rooms.models import Room
from users.models import KycDocument

User = get_user_model()


@tag("e2e")
class KYCVerifiedBadgeE2ETest(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="kyc_landlord",
            email="kyc_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=False,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _publish_room(self, title="KYC Test Studio"):
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": title,
                "description": "A bright studio awaiting KYC approval.",
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
        return Room.objects.get(pk=res.data["id"])

    def _room_payload(self, room_id):
        res = self.client.get(f"/api/v1/rooms/{room_id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data

    def test_kyc_approval_flips_badge_and_clears_fraud_signal(self):
        self._auth(self.landlord)
        room = self._publish_room()

        # 1. Unverified: no badge, owner unverified, fraud flags it.
        data = self._room_payload(room.pk)
        self.assertFalse(data["verified"])
        self.assertFalse(data["owner"]["nid_verified"])

        report = FraudReport.objects.get(room=room)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.UNVERIFIED_OWNER, detectors)

        # 2. Admin approves KYC (instance.save() so the signal fires).
        self.landlord.nid_verified = True
        self.landlord.save(update_fields=["nid_verified"])

        # 3. The badge data is now present on the listing…
        data = self._room_payload(room.pk)
        self.assertTrue(data["verified"])
        self.assertTrue(data["owner"]["nid_verified"])

        # …and a re-scan drops the unverified-owner signal.
        self._auth(self.landlord)
        res = self.client.post(f"/api/v1/fraud/rooms/{room.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        report.refresh_from_db()
        detectors = {s.detector for s in report.signals.all()}
        self.assertNotIn(FraudSignal.Detector.UNVERIFIED_OWNER, detectors)

        # 4. Revoking verification pulls the badges back off.
        self.landlord.nid_verified = False
        self.landlord.save(update_fields=["nid_verified"])
        self._auth(self.landlord)
        data = self._room_payload(room.pk)
        self.assertFalse(data["verified"])
        self.assertFalse(data["owner"]["nid_verified"])

    def test_kyc_sync_covers_all_of_a_landlords_listings(self):
        """KYC approval flips the badge on every listing, not just the newest."""
        self._auth(self.landlord)
        room_a = self._publish_room("KYC Studio A")
        room_b = self._publish_room("KYC Studio B")

        self.landlord.nid_verified = True
        self.landlord.save(update_fields=["nid_verified"])

        for room in (room_a, room_b):
            data = self._room_payload(room.pk)
            self.assertTrue(data["verified"], f"{room.title} should be verified")

    def test_saving_without_kyc_change_does_not_touch_rooms(self):
        """An unrelated profile save must not trigger the rooms update."""
        self._auth(self.landlord)
        room = self._publish_room()
        self.assertFalse(room.verified)

        self.landlord.phone = "01812345678"
        self.landlord.save(update_fields=["phone"])

        room.refresh_from_db()
        self.assertFalse(room.verified)

    def _make_roommate_profile(self, user, **overrides):
        self._auth(user)
        payload = {
            "budget_min": 8000,
            "budget_max": 15000,
            "preferred_area": "Mirpur",
            "room_type_pref": "studio",
            "gender_pref": "any",
            "lifestyle": ["clean", "student"],
            "occupation": "Engineer",
            "bio": "Looking for a tidy flatmate.",
            "move_in_date": "2026-09-01",
            "is_looking": True,
            **overrides,
        }
        res = self.client.put("/api/v1/roommates/profile/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        return res.data

    def test_roommate_matches_expose_kyc_state(self):
        """Match payloads carry nid_verified so verified users stand out."""
        verified_owner = User.objects.create_user(
            username="verified_owner",
            email="verified_owner@example.com",
            password="test12345",
            nid_verified=True,
        )
        unverified_owner = User.objects.create_user(
            username="unverified_owner",
            email="unverified_owner@example.com",
            password="test12345",
            nid_verified=False,
        )
        seeker = User.objects.create_user(
            username="seeker",
            email="seeker@example.com",
            password="test12345",
        )

        self._make_roommate_profile(verified_owner)
        self._make_roommate_profile(unverified_owner)
        self._make_roommate_profile(
            seeker,
            preferred_area="Mirpur",
            occupation="Student",
        )

        # The seeker asks for matches — both candidates are eligible.
        self._auth(seeker)
        res = self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(len(res.data), 2)

        by_username = {m["profile"]["user"]["username"]: m["profile"]["user"] for m in res.data}
        self.assertTrue(by_username["verified_owner"]["nid_verified"])
        self.assertFalse(by_username["unverified_owner"]["nid_verified"])


@tag("e2e")
class KycAdminPanelE2ETest(APITestCase):
    """Document upload + admin review panel, all through the real API."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="panel_landlord",
            email="panel_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=False,
        )
        self.admin = User.objects.create_user(
            username="panel_admin",
            email="panel_admin@example.com",
            password="test12345",
            role=User.Role.ADMIN,
            nid_verified=True,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _upload(self, user, doc_type="nid", name="nid.jpg"):
        self._auth(user)
        res = self.client.post(
            "/api/v1/users/kyc/documents/",
            {
                "doc_type": doc_type,
                "file": SimpleUploadedFile(name, b"fake-document-bytes", content_type="image/jpeg"),
            },
            format="multipart",
        )
        return res

    def _review(self, user, approved, note=""):
        self._auth(user)
        return self.client.post(
            f"/api/v1/users/kyc/{self.landlord.pk}/review/",
            {"approved": approved, "note": note},
            format="json",
        )

    def _publish_room(self):
        self._auth(self.landlord)
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": "Panel Studio",
                "description": "A studio waiting on KYC approval.",
                "room_type": "studio",
                "price": "11000.00",
                "area": "Mirpur",
                "address": "4 Mirpur Road",
                "lat": "23.8069",
                "lng": "90.3687",
                "amenities": ["WiFi"],
                "gender_preference": "any",
                "size_sqft": 300,
                "is_available": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return Room.objects.get(pk=res.data["id"])

    def test_landlord_uploads_and_owns_document(self):
        res = self._upload(self.landlord)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["doc_type"], "nid")
        # The file URL points at the authenticated endpoint, not the public
        # MEDIA_URL — the privacy contract of the KYC documents.
        self.assertIn("/users/kyc/documents/", res.data["file"])
        self.assertIn("/file/", res.data["file"])

        # GET my documents returns exactly the caller's own.
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/kyc/documents/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["id"], KycDocument.objects.get(user=self.landlord).pk)

    def test_documents_are_private_to_owner_and_admin(self):
        """A second non-admin user sees no foreign documents, and cannot fetch
        the landlord's file bytes (404 — no existence leak)."""
        res = self._upload(self.landlord)
        file_path = res.data["file"].replace("http://testserver", "")

        # Anonymous: the file endpoint demands auth.
        self.client.force_authenticate(user=None)
        res = self.client.get(file_path)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Another tenant: own list is empty and the file 404s for them.
        other = User.objects.create_user(
            username="other_tenant",
            email="other_tenant@example.com",
            password="test12345",
        )
        self._auth(other)
        res = self.client.get("/api/v1/users/kyc/documents/")
        self.assertEqual(len(res.data), 0)
        res = self.client.get(file_path)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # The owner can still fetch the bytes.
        self._auth(self.landlord)
        res = self.client.get(file_path)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(res.streaming_content), b"fake-document-bytes")

    def test_non_admin_cannot_access_panel(self):
        self._upload(self.landlord)
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/kyc/pending/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        res = self.client.post(
            f"/api/v1/users/kyc/{self.landlord.pk}/review/",
            {"approved": True},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_approves_kyc_through_panel(self):
        self._upload(self.landlord)
        room = self._publish_room()

        # Pending queue lists the landlord with the document attached.
        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/pending/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        usernames = {app["username"] for app in res.data}
        self.assertIn(self.landlord.username, usernames)
        entry = next(app for app in res.data if app["username"] == self.landlord.username)
        self.assertFalse(entry["nid_verified"])
        self.assertEqual(len(entry["documents"]), 1)
        self.assertEqual(entry["documents"][0]["status"], "pending")

        # Approve -> verified, document approved, audited, landlord notified.
        res = self._review(self.admin, True, note="Docs look genuine")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.landlord.refresh_from_db()
        self.assertTrue(self.landlord.nid_verified)

        doc = KycDocument.objects.get(user=self.landlord)
        self.assertEqual(doc.status, KycDocument.Status.APPROVED)
        self.assertEqual(doc.review_note, "Docs look genuine")

        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="kyc.approved", target_type="users.User", target_id=str(self.landlord.pk)
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord, notification_type="kyc_approved"
            ).exists()
        )

        # The listing badge flipped and a re-scan drops the fraud signal.
        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertTrue(res.data["verified"])
        self.assertTrue(res.data["owner"]["nid_verified"])
        res = self.client.post(f"/api/v1/fraud/rooms/{room.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        report = FraudReport.objects.get(room=room)
        self.assertNotIn(
            FraudSignal.Detector.UNVERIFIED_OWNER, {s.detector for s in report.signals.all()}
        )

    def test_admin_reject_marks_document_and_audits(self):
        self._upload(self.landlord)
        res = self._review(self.admin, False, note="Blurry scan — please re-upload")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

        self.landlord.refresh_from_db()
        self.assertFalse(self.landlord.nid_verified)
        doc = KycDocument.objects.get(user=self.landlord)
        self.assertEqual(doc.status, KycDocument.Status.REJECTED)
        self.assertEqual(doc.review_note, "Blurry scan — please re-upload")
        self.assertTrue(AuditLogEntry.objects.filter(action="kyc.rejected").exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord, notification_type="kyc_rejected"
            ).exists()
        )

        # Rejected applicant no longer appears in the pending queue.
        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/pending/")
        self.assertNotIn(self.landlord.username, {app["username"] for app in res.data})

    def test_upload_rejects_non_image_or_pdf(self):
        """Server-side guardrail: only images/PDFs up to 5 MB are accepted."""
        self._auth(self.landlord)
        res = self.client.post(
            "/api/v1/users/kyc/documents/",
            {
                "doc_type": "nid",
                "file": SimpleUploadedFile(
                    "evil.exe", b"MZ", content_type="application/x-msdownload"
                ),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, res.data)
        self.assertIn("file", res.data)
        self.assertFalse(KycDocument.objects.filter(user=self.landlord).exists())

    def test_admin_sees_kyc_audit_trail(self):
        """The approve/reject timeline comes from the append-only audit log."""
        self._upload(self.landlord)
        self._review(self.admin, True, note="Docs look genuine")
        self._review(self.admin, False, note="Revoked on appeal")

        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/audit/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual([e["action"] for e in res.data], ["kyc.rejected", "kyc.approved"])
        self.assertEqual(res.data[0]["note"], "Revoked on appeal")
        self.assertEqual(res.data[1]["note"], "Docs look genuine")
        self.assertEqual(res.data[1]["actor_username"], self.admin.username)
        self.assertEqual(res.data[1]["user_id"], self.landlord.pk)

        # A non-admin cannot read the trail.
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/kyc/audit/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_then_revoke_flips_badge_twice(self):
        self._upload(self.landlord)
        room = self._publish_room()

        self._review(self.admin, True)
        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertTrue(res.data["verified"])

        # Admin revokes verification -> badges come back off.
        self._auth(self.admin)
        res = self._review(self.admin, False, note="Suspicious re-submission")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.landlord.refresh_from_db()
        self.assertFalse(self.landlord.nid_verified)

        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertFalse(res.data["verified"])
        self.assertFalse(res.data["owner"]["nid_verified"])

    def test_admin_sees_kyc_sla_stats(self):
        """The SLA endpoint reports queue health: pending volume, decision
        speed and the 7-day trend — admin only."""
        from django.utils import timezone as tz

        # One pending doc (unresolved) + one resolved doc reviewed recently.
        self._upload(self.landlord)
        self._upload(self.admin)
        self._review(self.admin, True, note="Docs look genuine")

        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/sla/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["pending_count"], 1)
        self.assertEqual(res.data["resolved_count"], 1)
        self.assertIsNotNone(res.data["avg_review_hours"])
        self.assertEqual(res.data["last_7d_decisions"], 1)
        self.assertEqual(res.data["prev_7d_decisions"], 0)
        self.assertEqual(res.data["decision_delta_7d"], 1)
        self.assertIsNotNone(res.data["pending_oldest_hours"])
        # No breaches here (nothing old, trend positive) and a full 30-day
        # trend series — oldest first, today included.
        self.assertEqual(res.data["breaches"], [])
        self.assertEqual(len(res.data["trend_30d"]), 30)
        self.assertEqual(res.data["trend_30d"][-1]["date"], tz.localdate().isoformat())
        self.assertEqual(res.data["trend_30d"][-1]["decisions"], 1)

        # A non-admin cannot read SLA stats.
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/kyc/sla/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_sla_flags_oldest_pending_and_negative_trend(self):
        """The SLA endpoint flags a stuck queue (>48h oldest) and a slipping
        week (fewer decisions than last week)."""
        from datetime import timedelta

        from django.utils import timezone as tz

        # An old pending doc: created 3 days ago, never reviewed.
        old = KycDocument.objects.create(
            user=self.landlord,
            doc_type="nid",
            file=SimpleUploadedFile("old.jpg", b"x" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.PENDING,
        )
        KycDocument.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(days=3))

        # A resolved doc reviewed a week+ ago, so this week (0) trails last
        # week (1) -> trend_negative.
        old_resolved = KycDocument.objects.create(
            user=self.landlord,
            doc_type="passport",
            file=SimpleUploadedFile("old_resolved.jpg", b"y" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.APPROVED,
            reviewed_at=tz.now() - timedelta(days=10),
        )
        KycDocument.objects.filter(pk=old_resolved.pk).update(
            created_at=tz.now() - timedelta(days=11)
        )

        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/sla/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertIn("oldest_pending", res.data["breaches"])
        self.assertIn("trend_negative", res.data["breaches"])
        self.assertGreater(res.data["pending_oldest_hours"], 48)

    def test_sla_breach_task_alerts_admins_once_per_day(self):
        """The daily beat task notifies every admin (in-app + email) for each
        breached condition, deduplicated per day per condition."""
        from datetime import timedelta

        from django.core import mail
        from django.utils import timezone as tz

        from notifications.models import Notification
        from users.tasks import alert_kyc_sla_breaches

        # One ancient pending doc -> oldest_pending breach.
        old = KycDocument.objects.create(
            user=self.landlord,
            doc_type="nid",
            file=SimpleUploadedFile("old.jpg", b"x" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.PENDING,
        )
        KycDocument.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(days=3))

        with self.captureOnCommitCallbacks(execute=True):
            result = alert_kyc_sla_breaches()

        self.assertEqual(result["breaches"], ["oldest_pending"])
        self.assertGreater(result["alerted"], 0)
        # In-app notification created for the admin.
        self.assertTrue(
            Notification.objects.filter(notification_type=Notification.Type.KYC_SLA_BREACH).exists()
        )
        # Branded email with the queue deep-link.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("KYC queue breach", mail.outbox[0].subject)
        self.assertIn("/dashboard?tab=kyc", mail.outbox[0].body)

        # Running again the same day is a no-op (dedupe).
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            second = alert_kyc_sla_breaches()
        self.assertEqual(second["alerted"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sla_breach_task_broadcasts_over_websocket(self):
        """Every created alert notification is pushed live to the admin's
        notification channel group (the Navbar socket shows it instantly)."""
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone as tz

        from users.tasks import alert_kyc_sla_breaches

        old = KycDocument.objects.create(
            user=self.landlord,
            doc_type="nid",
            file=SimpleUploadedFile("old.jpg", b"x" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.PENDING,
        )
        KycDocument.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(days=3))

        with (
            patch("notifications.utils.broadcast_notification") as mock_broadcast,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = alert_kyc_sla_breaches()

        # One breach x one admin -> exactly one notification broadcast.
        self.assertEqual(result["websocket_pushed"], 1)
        self.assertEqual(mock_broadcast.call_count, 1)
        pushed = mock_broadcast.call_args.args[0]
        self.assertEqual(pushed.notification_type, Notification.Type.KYC_SLA_BREACH)
        self.assertEqual(pushed.user_id, self.admin.pk)

    def test_sla_breach_task_rate_limits_email_blast(self):
        """A multi-condition breach still respects the per-recipient daily
        budget: later emails are skipped, not sent."""
        from datetime import timedelta

        from django.core import mail
        from django.test import override_settings
        from django.utils import timezone as tz

        from notifications.models import EmailDeliveryLog
        from users.tasks import alert_kyc_sla_breaches

        # Two simultaneous breaches: stuck queue + slipping week.
        old = KycDocument.objects.create(
            user=self.landlord,
            doc_type="nid",
            file=SimpleUploadedFile("old.jpg", b"x" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.PENDING,
        )
        KycDocument.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(days=3))
        old_resolved = KycDocument.objects.create(
            user=self.landlord,
            doc_type="passport",
            file=SimpleUploadedFile("old_resolved.jpg", b"y" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.APPROVED,
            reviewed_at=tz.now() - timedelta(days=10),
        )
        KycDocument.objects.filter(pk=old_resolved.pk).update(
            created_at=tz.now() - timedelta(days=11)
        )

        with (
            override_settings(ALERT_EMAIL_DAILY_BUDGET=1),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = alert_kyc_sla_breaches()

        self.assertEqual(set(result["breaches"]), {"oldest_pending", "trend_negative"})
        self.assertEqual(result["alerted"], 2)
        # Both notifications were created and pushed; only the first email
        # went out, the second was throttled by the daily budget.
        self.assertEqual(result["emails_sent"], 1)
        self.assertEqual(result["emails_skipped"], 1)
        self.assertEqual(result["emails_failed"], 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            EmailDeliveryLog.objects.filter(status=EmailDeliveryLog.Status.SENT).count(), 1
        )
        skipped = EmailDeliveryLog.objects.get(status=EmailDeliveryLog.Status.SKIPPED)
        self.assertIn("daily budget", skipped.error)

    def test_sla_breach_task_logs_failed_email_without_raising(self):
        """A send failure is recorded in the delivery ledger and the task
        still completes — email is best-effort."""
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone as tz

        from notifications.models import EmailDeliveryLog
        from users.tasks import alert_kyc_sla_breaches

        old = KycDocument.objects.create(
            user=self.landlord,
            doc_type="nid",
            file=SimpleUploadedFile("old.jpg", b"x" * 10, content_type="image/jpeg"),
            status=KycDocument.Status.PENDING,
        )
        KycDocument.objects.filter(pk=old.pk).update(created_at=tz.now() - timedelta(days=3))

        # send_html_email failing (returning 0) simulates SMTP trouble.
        with (
            patch("notifications.email_guard.send_html_email", return_value=0),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = alert_kyc_sla_breaches()

        self.assertEqual(result["alerted"], 1)
        self.assertEqual(result["emails_failed"], 1)
        self.assertEqual(result["emails_sent"], 0)
        failed = EmailDeliveryLog.objects.get(status=EmailDeliveryLog.Status.FAILED)
        self.assertEqual(failed.recipient, self.admin.email)
        self.assertEqual(failed.template_name, "kyc_sla_alert")

    def test_rejection_sends_email_with_note_and_reupload_link(self):
        """Rejecting a document emails the landlord with the reviewer's note
        and a direct re-upload link; approving sends no rejection email.

        The email is sent via ``transaction.on_commit`` (never inside the
        atomic decision block), so the test must flush the on-commit
        callbacks — exactly what ``captureOnCommitCallbacks`` does.
        """
        from django.core import mail

        self._upload(self.landlord)
        with self.captureOnCommitCallbacks(execute=True):
            self._review(self.admin, False, note="Blurry scan — please re-upload")

        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn(self.landlord.email, msg.to)
        self.assertIn("needs attention", msg.subject)
        self.assertIn("Blurry scan — please re-upload", msg.body)
        self.assertIn("/dashboard?tab=kyc", msg.body)
        # The HTML alternative carries the branded CTA too.
        self.assertTrue(any("Re-upload your document" in c[0] for c in msg.alternatives))

        # Approving does not send the rejection email.
        self._upload(self.landlord)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self._review(self.admin, True, note="Looks good")
        self.assertEqual(len(mail.outbox), 0)

    def test_reject_then_upload_then_approve_full_loop(self):
        """The complete landlord lifecycle: upload -> reject (with note) -> the
        landlord sees the note -> re-uploads -> approve -> verified badge."""
        room = self._publish_room()

        # 1. First attempt: rejected with an actionable note.
        first = self._upload(self.landlord)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        res = self._review(self.admin, False, note="Blurry scan — please re-upload")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

        # 2. The landlord's document list exposes the rejection + the note.
        self._auth(self.landlord)
        res = self.client.get("/api/v1/users/kyc/documents/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        docs = {d["id"]: d for d in res.data}
        first_doc = docs[first.data["id"]]
        self.assertEqual(first_doc["status"], "rejected")
        self.assertEqual(first_doc["review_note"], "Blurry scan — please re-upload")

        # Still unverified, and the room carries no badge yet.
        self.landlord.refresh_from_db()
        self.assertFalse(self.landlord.nid_verified)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertFalse(res.data["verified"])

        # 3. Re-upload a fresh document -> pending again, queue shows the user.
        second = self._upload(self.landlord, doc_type="passport", name="passport.jpg")
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.data["status"], "pending")

        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/pending/")
        self.assertIn(self.landlord.username, {app["username"] for app in res.data})

        # 4. Admin approves -> verified; both docs resolved; badge flips.
        res = self._review(self.admin, True, note="Second attempt is clear")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.landlord.refresh_from_db()
        self.assertTrue(self.landlord.nid_verified)

        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertTrue(res.data["verified"])
        self.assertTrue(res.data["owner"]["nid_verified"])

        # The audit trail tells the whole story: rejected, then approved.
        self._auth(self.admin)
        res = self.client.get("/api/v1/users/kyc/audit/")
        self.assertEqual([e["action"] for e in res.data], ["kyc.approved", "kyc.rejected"])
        self.assertEqual(res.data[0]["note"], "Second attempt is clear")
        self.assertEqual(res.data[1]["note"], "Blurry scan — please re-upload")

        # The re-uploaded document is approved; the rejected first one stays.
        second_doc = KycDocument.objects.get(pk=second.data["id"])
        self.assertEqual(second_doc.status, KycDocument.Status.APPROVED)
        self.assertEqual(second_doc.review_note, "Second attempt is clear")
        first_doc_db = KycDocument.objects.get(pk=first.data["id"])
        self.assertEqual(first_doc_db.status, KycDocument.Status.REJECTED)
