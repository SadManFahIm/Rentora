"""Tests for the broker network — verification screening, referral
resolution, and the booking-approval commission signal.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from bookings.models import Booking
from monetization.models import Commission, RevenueLedgerEntry
from notifications.models import Notification
from rooms.models import Room

from .models import BrokerProfile, BrokerVerification
from .services import resolve_referral, screen_broker

User = get_user_model()


def make_room(owner, price=12000, **kw):
    defaults = dict(
        title="Broker Room",
        description="A test room.",
        room_type=Room.RoomType.SINGLE,
        price=price,
        area=Room.Area.DHANMONDI,
        address="Road 6",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi"],
        size_sqft=320,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, **defaults)


class ScreenBrokerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="screen_broker",
            email="screen@example.com",
            password="test12345",
            phone="01700000000",
            first_name="Sadman",
            last_name="Fahim",
        )
        self.profile = BrokerProfile.objects.create(user=self.user)

    def _screen(self, **profile_kw):
        for key, value in profile_kw.items():
            setattr(self.profile, key, value)
        self.profile.save()
        verification = BrokerVerification.objects.create(
            profile=self.profile, documents=["license.pdf"]
        )
        return screen_broker(verification)

    def test_complete_profile_recommends_approval(self):
        out = self._screen(
            license_number="BL-100",
            years_experience=3,
            specialization="Dhanmondi",
            areas=["Dhanmondi"],
        )
        self.assertEqual(out["score"], 100)
        self.assertEqual(out["result"], "recommend_approve")

    def test_missing_license_hard_fails(self):
        out = self._screen(years_experience=3, specialization="Dhanmondi", areas=["Dhanmondi"])
        self.assertTrue(any("no license number" in r for r in out["reasons"]))
        self.assertEqual(out["result"], "recommend_review")

    def test_no_documents_hard_fails(self):
        self.profile.license_number = "BL-100"
        self.profile.years_experience = 3
        self.profile.save()
        verification = BrokerVerification.objects.create(profile=self.profile, documents=[])
        out = screen_broker(verification)
        self.assertIn("no documents uploaded", out["reasons"])
        self.assertEqual(out["result"], "recommend_review")


class ReferralResolutionTests(TestCase):
    def setUp(self):
        self.broker = User.objects.create_user(
            username="ref_broker", email="ref@example.com", password="test12345"
        )
        self.verified = BrokerProfile.objects.create(
            user=self.broker, status=BrokerProfile.Status.VERIFIED
        )
        self.pending_user = User.objects.create_user(
            username="ref_pending", email="pending@example.com", password="test12345"
        )
        self.pending = BrokerProfile.objects.create(
            user=self.pending_user, status=BrokerProfile.Status.PENDING
        )

    def test_resolves_verified_only(self):
        self.assertEqual(resolve_referral(self.verified.referral_code).pk, self.verified.pk)
        self.assertIsNone(resolve_referral(self.pending.referral_code))
        self.assertIsNone(resolve_referral("NOPE0000"))
        self.assertIsNone(resolve_referral(""))


class BrokerCommissionSignalTests(TestCase):
    """A verified broker whose code was used earns a commission on approval."""

    def setUp(self):
        self.broker_user = User.objects.create_user(
            username="signal_broker", email="sig@example.com", password="test12345"
        )
        self.broker = BrokerProfile.objects.create(
            user=self.broker_user, status=BrokerProfile.Status.VERIFIED
        )
        self.owner = User.objects.create_user(
            username="signal_owner", email="owner@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="signal_tenant", email="tenant@example.com", password="test12345"
        )
        self.room = make_room(self.owner, price=12000)
        self.booking = Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.PENDING,
            check_in=date.today(),
            monthly_rent=Decimal("12000.00"),
            broker_referral=self.broker,
        )

    def _approve(self, booking):
        booking.status = Booking.Status.APPROVED
        booking.save()

    def test_approval_pays_idempotent_commission(self):
        self._approve(self.booking)
        commission = Commission.objects.get(idempotency_key=f"broker-booking-{self.booking.pk}")
        self.assertEqual(commission.amount, Decimal("240.00"))  # 2% of 12000
        self.assertEqual(commission.recipient, self.broker_user)

        # Ledger + notification recorded once.
        self.assertEqual(
            RevenueLedgerEntry.objects.filter(
                idempotency_key=f"broker-booking-ledger-{self.booking.pk}"
            ).count(),
            1,
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.broker_user,
                notification_type=Notification.Type.COMMISSION_EARNED,
            ).exists()
        )

        # Re-saving an approved booking never double-pays.
        self._approve(self.booking)
        self.assertEqual(Commission.objects.count(), 1)
        self.assertEqual(RevenueLedgerEntry.objects.filter(scope="broker").count(), 1)

    def test_unverified_broker_earns_nothing(self):
        self.broker.status = BrokerProfile.Status.PENDING
        self.broker.save()
        self._approve(self.booking)
        self.assertEqual(Commission.objects.count(), 0)

    def test_pending_booking_earns_nothing(self):
        self.assertEqual(Commission.objects.count(), 0)
        self.assertEqual(self.booking.created_at < timezone.now() + timedelta(hours=1), True)
