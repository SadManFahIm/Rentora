"""Booking lifecycle tests: request → approve → reject → cancel.

This is the tenant↔landlord agreement contract that drives every downstream
money flow (payment schedules, security deposits, invoices), so the state
transitions, who may perform them, and their guards are pinned down here.
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking
from notifications.models import Notification
from payments.models import PaymentSchedule
from rooms.models import Room

User = get_user_model()


class BookingLifecycleTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ll", email="ll@example.com", password="test12345", role=User.Role.LANDLORD
        )
        self.tenant = User.objects.create_user(
            username="tt", email="tt@example.com", password="test12345", role=User.Role.TENANT
        )
        self.tenant2 = User.objects.create_user(
            username="tt2", email="tt2@example.com", password="test12345", role=User.Role.TENANT
        )
        self.other = User.objects.create_user(
            username="xx", email="xx@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Lifecycle Room",
            description="Cozy single room near the lake.",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="12 Dhanmondi",
            lat=23.74,
            lng=90.37,
            amenities=["wifi"],
            size_sqft=180,
            is_available=True,
        )

    def _request_booking(self, user=None, **overrides):
        payload = {
            "room": self.room.pk,
            "check_in": "2026-01-15",
            "check_out": "2026-04-01",
            "notes": "Prefer early move-in.",
            **overrides,
        }
        self.client.force_authenticate(user or self.tenant)
        return self.client.post("/api/v1/bookings/", payload, format="json")

    def _booking_id(self):
        return Booking.objects.get(tenant=self.tenant).pk

    def test_tenant_requests_booking(self):
        res = self._request_booking()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        booking = Booking.objects.get(pk=res.data["id"])
        self.assertEqual(booking.status, Booking.Status.PENDING)
        # monthly_rent is never accepted from the client — it defaults to the room price.
        self.assertEqual(booking.monthly_rent, self.room.price)
        self.assertEqual(booking.tenant_id, self.tenant.id)
        # The landlord is notified of the incoming request.
        notif = self.landlord.notifications.filter(
            notification_type=Notification.Type.BOOKING_REQUEST
        ).latest("created_at")
        self.assertIn(self.room.title, notif.message)

    def test_cannot_book_own_room(self):
        res = self._request_booking(user=self.landlord)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("own room", str(res.data).lower())

    def test_cannot_book_unavailable_room(self):
        self.room.is_available = False
        self.room.save(update_fields=["is_available"])
        res = self._request_booking()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_overlapping_booking_is_rejected(self):
        first = self._request_booking()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        res = self._request_booking(
            user=self.tenant2, check_in="2026-02-01", check_out="2026-02-28"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overlapping", str(res.data).lower())

    def test_unauthenticated_booking_request(self):
        res = self.client.post(
            "/api/v1/bookings/",
            {"room": self.room.pk, "check_in": "2026-01-15"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_approves_and_payment_schedule_is_generated(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.status, Booking.Status.APPROVED)
        # Approval automatically creates the advance payment schedule
        # (Jan 15, Feb 15, Mar 15 — three installments before the Apr 1 end).
        schedule = list(booking.payment_schedules.all())
        self.assertEqual(len(schedule), 3)
        self.assertEqual(schedule[0].amount, booking.monthly_rent)
        self.assertEqual(schedule[0].status, PaymentSchedule.Status.UPCOMING)
        tenant_notif = self.tenant.notifications.filter(
            notification_type=Notification.Type.BOOKING_APPROVED
        ).latest("created_at")
        self.assertIn("approved", tenant_notif.title.lower())

    def test_owner_rejects(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "rejected"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.status, Booking.Status.REJECTED)
        self.assertTrue(
            self.tenant.notifications.filter(
                notification_type=Notification.Type.BOOKING_REJECTED
            ).exists()
        )
        # A rejected booking never generates a payment schedule.
        self.assertFalse(booking.payment_schedules.exists())

    def test_tenant_cancels_pending_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.tenant)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.CANCELLED)
        self.assertTrue(
            self.landlord.notifications.filter(
                notification_type=Notification.Type.BOOKING_CANCELLED
            ).exists()
        )

    def test_tenant_cancels_approved_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        self.client.patch(f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json")
        # No dates were checked out yet — the tenant may still back out.
        self.client.force_authenticate(self.tenant)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.CANCELLED)

    def test_tenant_cannot_approve_own_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.tenant)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.PENDING)

    def test_landlord_cannot_cancel_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.PENDING)

    def test_cannot_reject_an_approved_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        self.client.patch(f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json")
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "rejected"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.APPROVED)

    def test_unrelated_user_cannot_update_booking(self):
        self._request_booking()
        booking_id = self._booking_id()
        self.client.force_authenticate(self.other)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
        )
        # The scoped queryset hides the booking entirely → 404, not 403.
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_bookings_visible_only_to_participants(self):
        self._request_booking()
        booking_id = self._booking_id()
        for user in (self.tenant, self.landlord):
            self.client.force_authenticate(user)
            res = self.client.get(f"/api/v1/bookings/{booking_id}/")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.other)
        res = self.client.get(f"/api/v1/bookings/{booking_id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_agreement_can_only_be_signed_when_approved(self):
        self._request_booking()
        booking_id = self._booking_id()
        # Pending → signing blocked.
        self.client.force_authenticate(self.tenant)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"agreement_signed": True}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # Approved → both parties may sign.
        self.client.force_authenticate(self.landlord)
        self.client.patch(f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json")
        self.client.force_authenticate(self.tenant)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"agreement_signed": True}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertTrue(Booking.objects.get(pk=booking_id).agreement_signed)

    def test_approval_blocks_on_unpaid_deposit_when_required(self):
        self._request_booking(security_deposit_amount=5000)
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        with override_settings(REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL=True):
            res = self.client.patch(
                f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("security deposit", str(res.data).lower())
            self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.PENDING)
            # Once the deposit clears, the same approval succeeds.
            Booking.objects.filter(pk=booking_id).update(security_deposit_paid=True)
            res = self.client.patch(
                f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.APPROVED)

    def test_deposit_not_required_by_default(self):
        """With the business rule off (default), an unpaid deposit never blocks approval."""
        self._request_booking(security_deposit_amount=5000)
        booking_id = self._booking_id()
        self.client.force_authenticate(self.landlord)
        res = self.client.patch(
            f"/api/v1/bookings/{booking_id}/", {"status": "approved"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.APPROVED)

    def test_deposit_status_endpoint(self):
        self._request_booking(security_deposit_amount=5000)
        booking_id = self._booking_id()
        self.client.force_authenticate(self.tenant)
        res = self.client.get(f"/api/v1/bookings/{booking_id}/deposit-status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["security_deposit_amount"], 5000.0)
        self.assertFalse(res.data["required_before_approval"])  # rule off by default
        with override_settings(REQUIRE_SECURITY_DEPOSIT_BEFORE_APPROVAL=True):
            res = self.client.get(f"/api/v1/bookings/{booking_id}/deposit-status/")
            self.assertTrue(res.data["required_before_approval"])
