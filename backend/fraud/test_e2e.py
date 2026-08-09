"""E2E integration: fraud auto-scan x booking flow, through the real API.

Walks one continuous story across the whole stack — no detector or task
functions are called directly, everything happens through HTTP the way a
browser would:

1. Landlord lists a room  → ``post_save`` fires the auto-scan through the
   Celery queue (eager mode in tests) → low-severity report, no interruption.
2. Landlord lists a duplicate title → auto-scan flags it HIGH → in-app
   notification + branded fraud email to the landlord, public badge flips.
3. Tenant books the *flagged* room → landlord gets a "New booking request"
   notification + email (booking flow is unaffected by a flagged listing).
4. Landlord approves → tenant notified + emailed, payment schedule created.
5. Re-scan cycle: landlord fixes the title, adds a photo, re-scans explicitly
   → report goes clean, badge flips back, the approved booking is untouched.

This is the contract the product promises: detection never blocks listing,
booking, or approving; and a re-scan after a fix always reflects reality.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from bookings.models import Booking
from fraud.models import FraudReport, FraudSignal
from notifications.models import Notification
from payments.models import PaymentSchedule
from rooms.models import Room

User = get_user_model()


def _room_payload(title, description, **overrides):
    """Shared room POST body. Area + title drive the duplicate premise —
    every listing here shares area="Mirpur" and, for flag tests, a title."""
    payload = {
        "title": title,
        "description": description,
        "room_type": "studio",
        "price": "15000.00",
        "area": "Mirpur",
        "address": "12 Mirpur Road",
        "lat": "23.8069",
        "lng": "90.3687",
        "amenities": ["WiFi", "AC"],
        "gender_preference": "any",
        "size_sqft": 350,
        "is_available": True,
        **overrides,
    }
    return payload


@tag("e2e")
class FraudBookingE2ETest(APITestCase):
    """End-to-end cycle: create → flag → landlord email → booking → re-scan."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="landlord",
            email="landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=True,
        )
        self.tenant = User.objects.create_user(
            username="tenant",
            email="tenant@example.com",
            password="test12345",
            role=User.Role.TENANT,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _create_room(self, title, **overrides):
        payload = _room_payload(
            title,
            overrides.pop("description", "A distinct, well-written description for this listing."),
            **overrides,
        )
        return self.client.post("/api/v1/rooms/", payload, format="json")

    def test_full_fraud_and_booking_cycle(self):
        # ---- 1. First listing: auto-scan scores it, but LOW is informational ----
        self._auth(self.landlord)
        res = self._create_room(
            "Sunrise Studio, Mirpur", description="Sunny studio right next to the metro."
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        first_id = res.data["id"]

        report = FraudReport.objects.get(room_id=first_id)
        self.assertEqual(report.severity, FraudReport.Severity.LOW)  # missing images only
        # LOW does not interrupt the landlord: no notification, no email.
        self.assertEqual(self.landlord.notifications.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

        # ---- 2. Duplicate title → auto-scan flags HIGH and alerts the landlord ----
        res = self._create_room(
            "Sunrise Studio, Mirpur",
            description="Completely different copy, no duplication here.",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        dup = Room.objects.get(pk=res.data["id"])

        report = dup.fraud_report
        self.assertEqual(report.severity, FraudReport.Severity.HIGH)
        self.assertEqual(report.score, 100)
        self.assertTrue(report.is_flagged)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.DUPLICATE_LISTING, detectors)

        # In-app notification…
        notif = self.landlord.notifications.filter(notification_type="fraud_flag").latest(
            "created_at"
        )
        self.assertIn("flagged", notif.title.lower())
        self.assertIn(dup.title, notif.message)

        # …and the branded fraud email (HTML alternative attached).
        self.assertEqual(len(mail.outbox), 1)
        flag_email = mail.outbox[-1]
        self.assertEqual(flag_email.to, [self.landlord.email])
        self.assertIn("was flagged", flag_email.subject)
        self.assertTrue(flag_email.alternatives, "fraud email must carry an HTML body")

        # Public badge for the listing says flagged.
        badge = self.client.get(f"/api/v1/fraud/rooms/{dup.pk}/status/")
        self.assertEqual(badge.status_code, status.HTTP_200_OK)
        self.assertTrue(badge.data["flagged"])
        self.assertEqual(badge.data["severity"], FraudReport.Severity.HIGH)

        # ---- 3. Booking flow on the flagged room still works ----
        self._auth(self.tenant)
        res = self.client.post(
            "/api/v1/bookings/",
            {
                "room": dup.pk,
                "check_in": str(date.today() + timedelta(days=7)),
                "check_out": str(date.today() + timedelta(days=70)),
                "notes": "Prefers the ground floor.",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        booking = Booking.objects.get(pk=res.data["id"])

        # Owner is notified + emailed about the request (2nd email overall).
        owner_notif = self.landlord.notifications.filter(
            notification_type=Notification.Type.BOOKING_REQUEST
        ).latest("created_at")
        self.assertIn(dup.title, owner_notif.message)
        self.assertEqual(len(mail.outbox), 2)
        request_email = mail.outbox[-1]
        self.assertEqual(request_email.subject, "New booking request")
        self.assertEqual(request_email.to, [self.landlord.email])

        # ---- 4. Landlord approves → tenant notified + emailed, schedule created ----
        self._auth(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking.pk}/", {"status": "approved"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.APPROVED)

        tenant_notif = self.tenant.notifications.filter(
            notification_type=Notification.Type.BOOKING_APPROVED
        ).latest("created_at")
        self.assertIn(dup.title, tenant_notif.message)
        self.assertEqual(len(mail.outbox), 3)
        approve_email = mail.outbox[-1]
        self.assertEqual(approve_email.to, [self.tenant.email])
        self.assertIn("approved", approve_email.subject.lower())

        schedule = PaymentSchedule.objects.filter(booking=booking)
        self.assertGreaterEqual(schedule.count(), 1, "approval should mint a payment schedule")

        # ---- 5. Re-scan cycle: fix → explicit re-scan → clean, badge flips ----
        self._auth(self.landlord)
        res = self.client.patch(
            f"/api/v1/rooms/{dup.pk}/", {"title": "Garden View Studio, Mirpur"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        # No images endpoint exists in the API surface, so the photo is seeded
        # via the ORM — the only non-HTTP step in this story.
        dup.images.create(image="http://example.com/room.jpg", is_primary=True)

        # Documented contract: an edit alone does NOT re-scan — still HIGH until
        # the landlord (or admin) explicitly re-scans.
        dup.fraud_report.refresh_from_db()
        self.assertEqual(dup.fraud_report.severity, FraudReport.Severity.HIGH)

        res = self.client.post(f"/api/v1/fraud/rooms/{dup.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        dup.fraud_report.refresh_from_db()
        self.assertEqual(dup.fraud_report.severity, FraudReport.Severity.CLEAN)
        self.assertEqual(dup.fraud_report.score, 0)
        self.assertEqual(dup.fraud_report.signals.count(), 0)

        badge = self.client.get(f"/api/v1/fraud/rooms/{dup.pk}/status/")
        self.assertFalse(badge.data["flagged"])
        self.assertEqual(badge.data["score"], 0)

        # A clean re-scan must not re-alert the landlord (clean != alert).
        self.assertEqual(
            self.landlord.notifications.filter(notification_type="fraud_flag").count(),
            1,
        )

        # The re-scan must not disturb the live booking.
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.APPROVED)
        self.assertEqual(booking.room_id, dup.pk)

    def test_rejected_booking_on_flagged_room_emails_tenant(self):
        """Booking lifecycle around a flagged room: reject → tenant email."""
        self._auth(self.landlord)
        self._create_room("Metro View, Mirpur", description="Views for days.")
        res = self._create_room("Metro View, Mirpur", description="Entirely original copy.")
        dup = Room.objects.get(pk=res.data["id"])
        self.assertTrue(dup.fraud_report.is_flagged)

        # Tenant books the flagged room; landlord rejects it.
        self._auth(self.tenant)
        res = self.client.post(
            "/api/v1/bookings/",
            {
                "room": dup.pk,
                "check_in": str(date.today() + timedelta(days=3)),
                "notes": "Short stay.",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        booking = Booking.objects.get(pk=res.data["id"])

        self._auth(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking.pk}/", {"status": "rejected"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

        reject_email = mail.outbox[-1]
        self.assertEqual(reject_email.to, [self.tenant.email])
        self.assertIn("declined", reject_email.subject.lower())


@tag("e2e")
class FraudAdminReviewE2ETest(APITestCase):
    """Admin resolution flow: flag → review / dismiss, all through the API.

    Extends the audit-log unit tests into a full chain: the flagged report is
    produced by the auto-scan (not a direct ``run_scan`` call), the decision
    goes through ``POST /fraud/reports/{id}/review/``, the audit trail is
    checked end-to-end, and the list endpoint's status filters are verified.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="landlord",
            email="landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=True,
        )
        self.admin = User.objects.create_user(
            username="boss",
            email="boss@example.com",
            password="test12345",
            is_staff=True,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _post_duplicate(self, description):
        """Post a room that duplicates the previous one; returns the new room."""
        res = self.client.post(
            "/api/v1/rooms/", _room_payload("Modern Studio, Mirpur", description), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return Room.objects.get(pk=res.data["id"])

    def test_admin_reviews_and_dismisses_flagged_reports(self):
        # Two duplicate listings → two HIGH reports, both open (auto-scan).
        self._auth(self.landlord)
        self._post_duplicate("Original first listing.")
        room_b = self._post_duplicate("Entirely separate copy B.")
        room_c = self._post_duplicate("Entirely separate copy C.")
        report_b = room_b.fraud_report
        report_c = room_c.fraud_report
        self.assertEqual(report_b.severity, FraudReport.Severity.HIGH)
        self.assertEqual(report_c.severity, FraudReport.Severity.HIGH)
        self.assertEqual(report_b.status, FraudReport.Status.OPEN)

        # A landlord (non-admin) cannot resolve reports.
        res = self.client.post(
            f"/api/v1/fraud/reports/{report_b.pk}/review/",
            {"action": "reviewed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin reviews report B → status flips + audit entry written.
        self._auth(self.admin)
        res = self.client.post(
            f"/api/v1/fraud/reports/{report_b.pk}/review/",
            {"action": "reviewed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        report_b.refresh_from_db()
        self.assertEqual(report_b.status, FraudReport.Status.REVIEWED)

        entry = AuditLogEntry.objects.filter(action="fraud.report.reviewed").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_type, "fraud.FraudReport")
        self.assertEqual(entry.target_id, str(report_b.pk))
        self.assertEqual(entry.detail, {"room_id": room_b.pk})

        # Admin dismisses report C.
        res = self.client.post(
            f"/api/v1/fraud/reports/{report_c.pk}/review/",
            {"action": "dismissed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        report_c.refresh_from_db()
        self.assertEqual(report_c.status, FraudReport.Status.DISMISSED)
        self.assertTrue(AuditLogEntry.objects.filter(action="fraud.report.dismissed").exists())

        # Status filters on the list endpoint reflect both decisions.
        res = self.client.get("/api/v1/fraud/reports/?status=reviewed")
        self.assertEqual({r["id"] for r in res.data}, {report_b.pk})
        res = self.client.get("/api/v1/fraud/reports/?status=dismissed")
        self.assertEqual({r["id"] for r in res.data}, {report_c.pk})

        # The audit trail is append-only: exactly one entry per decision.
        self.assertEqual(
            AuditLogEntry.objects.filter(action__startswith="fraud.report.").count(),
            2,
        )

    def test_review_keeps_reports_visible_in_admin_list(self):
        """Reviewed reports still appear in the unfiltered admin list."""
        self._auth(self.landlord)
        self._post_duplicate("Original listing.")
        room = self._post_duplicate("Distinct copy.")
        report = room.fraud_report

        self._auth(self.admin)
        res = self.client.post(
            f"/api/v1/fraud/reports/{report.pk}/review/",
            {"action": "reviewed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

        res = self.client.get("/api/v1/fraud/reports/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(report.pk, {r["id"] for r in res.data})
        by_id = next(r for r in res.data if r["id"] == report.pk)
        self.assertEqual(by_id["status"], FraudReport.Status.REVIEWED)
