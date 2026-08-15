"""Phase 12 — dispute resolution tests.

Covers: eligibility (approved bookings only, one open dispute), participant
authorization (IDOR guard — outsiders get 404), evidence submission, admin
queue access, audited transitions, and deposit-outcome resolution.
"""

from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from bookings.models import Booking
from notifications.models import Notification
from rooms.models import Room

from .models import Dispute, DisputeEvidence

User = get_user_model()


def make_room(owner, title="Dispute Room"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="d",
        room_type="single",
        price=9000,
        area="Mirpur",
        address="x",
        lat=23.8,
        lng=90.4,
        amenities=["wifi"],
        size_sqft=200,
    )


class DisputeTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="dadmin", email="da@e.com", password="x", is_staff=True
        )
        self.landlord = User.objects.create_user(username="dl", email="dl@e.com", password="x")
        self.tenant = User.objects.create_user(username="dt", email="dt@e.com", password="x")
        self.room = make_room(self.landlord)
        self.booking = Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 1),
            monthly_rent=9000,
            security_deposit_amount=5000,
            security_deposit_paid=True,
        )

    def open_dispute(self, user, booking=None, category="deposit"):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/v1/disputes/",
            {
                "booking": (booking or self.booking).pk,
                "category": category,
                "description": "Deposit not returned.",
            },
            format="json",
        )

    def test_tenant_opens_dispute_and_landlord_is_notified(self):
        res = self.open_dispute(self.tenant)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        dispute = Dispute.objects.get(pk=res.data["id"])
        self.assertEqual(dispute.status, Dispute.Status.OPEN)
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord, notification_type=Notification.Type.DISPUTE_OPENED
            ).exists()
        )
        # Landlord sees it in their list.
        self.client.force_authenticate(self.landlord)
        res = self.client.get("/api/v1/disputes/")
        self.assertEqual(len(res.data), 1)

    def test_cannot_open_dispute_on_pending_booking(self):
        pending = Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.PENDING,
            check_in=date(2026, 3, 1),
            monthly_rent=9000,
        )
        res = self.open_dispute(self.tenant, booking=pending)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_one_open_dispute_per_booking(self):
        self.open_dispute(self.tenant)
        res = self.open_dispute(self.tenant, category="payment")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Dispute.objects.count(), 1)

    def test_non_party_cannot_open_or_read(self):
        stranger = User.objects.create_user(username="ds", email="ds@e.com", password="x")
        res = self.open_dispute(stranger)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(stranger)
        self.assertEqual(
            self.client.get(f"/api/v1/disputes/{dispute.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_parties_add_evidence(self):
        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            f"/api/v1/disputes/{dispute.pk}/evidence/",
            {"kind": "text", "content": "The deposit covers a broken window."},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(DisputeEvidence.objects.count(), 1)
        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant, notification_type=Notification.Type.DISPUTE_UPDATE
            ).exists()
        )
        # Tenant sees the evidence in the detail view.
        self.client.force_authenticate(self.tenant)
        detail = self.client.get(f"/api/v1/disputes/{dispute.pk}/")
        self.assertEqual(len(detail.data["evidence"]), 1)

    def test_closed_dispute_rejects_new_evidence(self):
        dispute = Dispute.objects.create(
            booking=self.booking,
            opened_by=self.tenant,
            category=Dispute.Category.DEPOSIT,
            status=Dispute.Status.RESOLVED,
        )
        self.client.force_authenticate(self.tenant)
        res = self.client.post(
            f"/api/v1/disputes/{dispute.pk}/evidence/",
            {"kind": "text", "content": "late"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_transition_audits_and_notifies(self):
        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/disputes/admin/{dispute.pk}/action/",
            {"action": "transition", "status": "waiting_for_landlord"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, Dispute.Status.WAITING_FOR_LANDLORD)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="dispute.transition", target_id=str(dispute.pk)
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord, notification_type=Notification.Type.DISPUTE_UPDATE
            ).exists()
        )

    def test_admin_resolve_with_deposit_refund_updates_booking(self):
        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/disputes/admin/{dispute.pk}/action/",
            {
                "action": "resolve",
                "decision": "refund_to_tenant",
                "decision_amount": "5000.00",
                "resolution": "Deposit returned in full.",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, Dispute.Status.RESOLVED)
        self.assertEqual(dispute.decision, Dispute.Decision.REFUND_TO_TENANT)
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.security_deposit_refunded)
        self.assertTrue(AuditLogEntry.objects.filter(action="dispute.resolve").exists())

    def test_admin_reject_closes_dispute(self):
        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            f"/api/v1/disputes/admin/{dispute.pk}/action/",
            {"action": "reject", "resolution": "No evidence of damage."},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, Dispute.Status.REJECTED)
        self.assertTrue(AuditLogEntry.objects.filter(action="dispute.reject").exists())

    def test_admin_endpoints_require_admin(self):
        dispute = Dispute.objects.create(
            booking=self.booking, opened_by=self.tenant, category=Dispute.Category.DEPOSIT
        )
        self.client.force_authenticate(self.tenant)
        self.assertEqual(
            self.client.get("/api/v1/disputes/admin/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/disputes/admin/{dispute.pk}/action/",
                {"action": "transition", "status": "escalated"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
