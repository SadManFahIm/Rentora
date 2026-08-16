"""Tests for Tier-3 tenant behavioral trust signals.

The signal must be backed by real, provable data: an approved booking counts
as "completed" only when the deposit was refunded or the check-out date
passed. Pending/approved-in-progress stays must NOT count.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from bookings.models import Booking
from rooms.models import Room
from users.trust import completed_bookings_count, trust_signals

User = get_user_model()


def make_user(username, tenant=True):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        phone="01712345678",
        nid_verified=False,
        tenant_verified=tenant,
    )


def make_room(owner):
    return Room.objects.create(
        owner=owner,
        title="Trust Room",
        description="A room.",
        room_type="single",
        price=9000,
        area="Uttara",
        address="Sector 4, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=200,
    )


def make_booking(tenant, room, status=Booking.Status.APPROVED, refunded=False, check_out=None):
    return Booking.objects.create(
        room=room,
        tenant=tenant,
        status=status,
        check_in=date.today() - timedelta(days=30),
        check_out=check_out or (date.today() + timedelta(days=30)),
        monthly_rent=9000,
        security_deposit_amount=9000,
        security_deposit_paid=True,
        security_deposit_refunded=refunded,
    )


class CompletedBookingsCountTests(TestCase):
    def setUp(self):
        self.landlord = make_user("cl_landlord", tenant=False)
        self.tenant = make_user("cl_tenant")
        self.room = make_room(self.landlord)

    def test_zero_when_no_bookings(self):
        self.assertEqual(completed_bookings_count(self.tenant), 0)

    def test_approved_in_progress_does_not_count(self):
        make_booking(self.tenant, self.room)  # approved, stay ongoing
        self.assertEqual(completed_bookings_count(self.tenant), 0)

    def test_refunded_deposit_counts(self):
        make_booking(self.tenant, self.room, refunded=True)
        self.assertEqual(completed_bookings_count(self.tenant), 1)

    def test_past_checkout_counts(self):
        make_booking(self.tenant, self.room, check_out=date.today() - timedelta(days=1))
        self.assertEqual(completed_bookings_count(self.tenant), 1)

    def test_cancelled_or_pending_never_count(self):
        make_booking(self.tenant, self.room, status=Booking.Status.PENDING)
        make_booking(
            self.tenant,
            self.room,
            status=Booking.Status.CANCELLED,
            check_out=date.today() - timedelta(days=5),
        )
        self.assertEqual(completed_bookings_count(self.tenant), 0)

    def test_does_not_count_other_tenants(self):
        other = make_user("cl_other")
        make_booking(other, self.room, refunded=True)
        self.assertEqual(completed_bookings_count(self.tenant), 0)


class TrustSignalsDictTests(TestCase):
    def setUp(self):
        self.landlord = make_user("ts_landlord", tenant=False)
        self.tenant = make_user("ts_tenant")

    def test_identity_flags_reflected(self):
        signals = trust_signals(self.tenant)
        self.assertTrue(signals["tenant_verified"])
        self.assertFalse(signals["nid_verified"])

    def test_none_user_safe(self):
        signals = trust_signals(None)
        self.assertEqual(signals["completed_bookings"], 0)
        self.assertFalse(signals["tenant_verified"])

    def test_completed_bookings_included(self):
        room = make_room(self.landlord)
        make_booking(self.tenant, room, refunded=True)
        self.assertEqual(trust_signals(self.tenant)["completed_bookings"], 1)

    def test_no_internal_scores_leaked(self):
        signals = trust_signals(self.tenant)
        for forbidden in ("fraud", "risk", "score"):
            self.assertNotIn(forbidden, signals)


class TrustSignalsApiTests(APITestCase):
    def setUp(self):
        self.landlord = make_user("api_landlord", tenant=False)
        self.tenant = make_user("api_tenant")
        self.room = make_room(self.landlord)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_user_details_carries_trust_signals(self):
        self._auth(self.tenant)
        res = self.client.get("/api/v1/auth/user/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        signals = res.data["trust_signals"]
        self.assertEqual(signals["completed_bookings"], 0)
        self.assertTrue(signals["tenant_verified"])

    def test_booking_payload_carries_tenant_signals(self):
        booking = make_booking(self.tenant, self.room, refunded=True)
        self._auth(self.landlord)
        res = self.client.get(f"/api/v1/bookings/{booking.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        signals = res.data["tenant_trust_signals"]
        self.assertEqual(signals["completed_bookings"], 1)
        self.assertTrue(signals["tenant_verified"])

    def test_chat_participant_carries_signals(self):
        make_booking(self.tenant, self.room, refunded=True)
        self._auth(self.tenant)
        # Start a chat with the landlord -> the other participant exposes signals.
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.landlord.pk}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res2 = self.client.get(f"/api/v1/chat/rooms/{res.data['id']}/")
        participants = res2.data["participants"]
        landlord = next(p for p in participants if p["id"] == self.landlord.pk)
        self.assertIn("trust_signals", landlord)
        self.assertIn("completed_bookings", landlord["trust_signals"])
