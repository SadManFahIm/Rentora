"""Tests for corporate housing — account RBAC, bulk bookings (partial
success), and idempotent period invoicing.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from bookings.models import Booking
from rooms.models import Room

from .models import CorporateAccount, CorporateInvoice, CorporateMember
from .services import (
    accounts_for,
    bulk_create_bookings,
    can_manage_account,
    generate_invoice,
)

User = get_user_model()


def make_room(owner, price=10000, **kw):
    defaults = dict(
        title="Corporate Room",
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


class CorporateRBACTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="corp_owner", email="co@example.com", password="test12345"
        )
        self.admin_member = User.objects.create_user(
            username="corp_admin", email="ca@example.com", password="test12345"
        )
        self.member = User.objects.create_user(
            username="corp_member", email="cm@example.com", password="test12345"
        )
        self.stranger = User.objects.create_user(
            username="corp_stranger", email="cs@example.com", password="test12345"
        )
        self.platform_admin = User.objects.create_user(
            username="corp_super", email="csup@example.com", password="test12345", is_staff=True
        )
        self.account = CorporateAccount.objects.create(name="ACME Ltd", owner=self.owner)
        CorporateMember.objects.create(account=self.account, user=self.admin_member, role="admin")
        CorporateMember.objects.create(account=self.account, user=self.member, role="member")

    def test_can_manage_account(self):
        self.assertTrue(can_manage_account(self.owner, self.account))
        self.assertTrue(can_manage_account(self.admin_member, self.account))
        self.assertTrue(can_manage_account(self.platform_admin, self.account))
        self.assertFalse(can_manage_account(self.member, self.account))
        self.assertFalse(can_manage_account(self.stranger, self.account))

    def test_accounts_for(self):
        self.assertEqual(list(accounts_for(self.owner)), [self.account])
        self.assertEqual(list(accounts_for(self.member)), [self.account])
        self.assertEqual(list(accounts_for(self.platform_admin)), [self.account])
        self.assertEqual(list(accounts_for(self.stranger)), [])


class BulkBookingTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="bulk_owner", email="bo@example.com", password="test12345"
        )
        self.corp_owner = User.objects.create_user(
            username="bulk_corp", email="bc@example.com", password="test12345"
        )
        self.account = CorporateAccount.objects.create(name="Widgets Inc", owner=self.corp_owner)
        self.room = make_room(self.owner, price=11000)

    def test_bulk_creates_member_bookings(self):
        result = bulk_create_bookings(
            account=self.account,
            room=self.room,
            check_in=date(2026, 9, 1),
            check_out=date(2027, 2, 1),
            members=[
                {"email": "a@widgets.com", "first_name": "A"},
                {"email": "b@widgets.com", "first_name": "B"},
                {"email": "c@widgets.com", "first_name": "C"},
            ],
        )
        self.assertEqual(result["created_count"], 3)
        self.assertEqual(result["errors"], [])
        bookings = Booking.objects.filter(corporate_account=self.account)
        self.assertEqual(bookings.count(), 3)
        self.assertTrue(all(b.status == Booking.Status.PENDING for b in bookings))
        self.assertEqual(bookings.first().monthly_rent, self.room.price)

    def test_partial_success_isolates_bad_rows(self):
        result = bulk_create_bookings(
            account=self.account,
            room=self.room,
            check_in=date(2026, 9, 1),
            check_out=date(2027, 2, 1),
            members=[
                {"email": "good@widgets.com", "first_name": "Good"},
                {"email": "bad@widgets.com", "monthly_rent": "not-a-number"},
                {"email": "fine@widgets.com", "first_name": "Fine"},
            ],
        )
        self.assertEqual(result["created_count"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["index"], 1)


class InvoiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="inv_owner", email="io@example.com", password="test12345"
        )
        self.corp_owner = User.objects.create_user(
            username="inv_corp", email="ic@example.com", password="test12345"
        )
        self.account = CorporateAccount.objects.create(name="Mega Co", owner=self.corp_owner)
        self.room = make_room(self.owner, price=10000)
        self.period_start = date(2026, 10, 1)
        self.period_end = date(2026, 10, 31)

    def _booking(self, rent, status):
        return Booking.objects.create(
            room=self.room,
            tenant=self.corp_owner,
            status=status,
            check_in=date(2026, 10, 1),
            monthly_rent=Decimal(rent),
            corporate_account=self.account,
        )

    def test_invoice_sums_approved_bookings_only(self):
        self._booking("10000", Booking.Status.APPROVED)
        self._booking("20000", Booking.Status.APPROVED)
        self._booking("99999", Booking.Status.PENDING)
        invoice = generate_invoice(self.account, self.period_start, self.period_end)
        self.assertEqual(invoice.amount, Decimal("30000.00"))
        self.assertEqual(len(invoice.line_items), 2)
        self.assertTrue(invoice.invoice_number.startswith("CORP-"))

    def test_invoice_is_idempotent_by_period(self):
        self._booking("10000", Booking.Status.APPROVED)
        first = generate_invoice(self.account, self.period_start, self.period_end)
        second = generate_invoice(self.account, self.period_start, self.period_end)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(CorporateInvoice.objects.count(), 1)

    def test_different_period_gets_own_invoice(self):
        self._booking("10000", Booking.Status.APPROVED)
        generate_invoice(self.account, self.period_start, self.period_end)
        later = generate_invoice(self.account, self.period_start, date(2026, 11, 30))
        self.assertEqual(later.period_start, self.period_start)
        self.assertNotEqual(later.period_end, self.period_end)
        self.assertEqual(CorporateInvoice.objects.count(), 2)

    def test_check_in_outside_period_excluded(self):
        Booking.objects.create(
            room=self.room,
            tenant=self.corp_owner,
            status=Booking.Status.APPROVED,
            check_in=date(2027, 1, 1),  # starts after the period
            monthly_rent=Decimal("10000"),
            corporate_account=self.account,
        )
        invoice = generate_invoice(self.account, self.period_start, self.period_end)
        self.assertEqual(invoice.amount, Decimal("0.00"))
