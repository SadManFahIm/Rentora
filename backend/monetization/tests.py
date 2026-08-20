"""Tests for the monetization core — commission engine, revenue ledger,
payout lifecycle. Money discipline: idempotent by key, Decimal math,
masked account details, audit-trailed transitions.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry

from .models import Commission, CommissionRule, Payout, RevenueLedgerEntry
from .services.commissions import commission_amount, commission_rate, create_commission
from .services.ledger import record_entry
from .services.payouts import PayoutError, available_balance, request_payout

User = get_user_model()


class CommissionRateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rate_user", email="rate@example.com", password="test12345"
        )

    def test_default_fallback(self):
        self.assertEqual(commission_rate("broker"), Decimal("2.00"))

    def test_active_rule_overrides_default(self):
        CommissionRule.objects.create(scope="broker", rate=5.5)
        self.assertEqual(commission_rate("broker"), Decimal("5.50"))

    def test_override_beats_rule(self):
        CommissionRule.objects.create(scope="broker", rate=5.5)
        self.assertEqual(commission_rate("broker", override=3), Decimal("3.00"))

    def test_amount_math(self):
        self.assertEqual(commission_amount(Decimal("10000"), Decimal("2.50")), Decimal("250.00"))
        # Half-paisa rounding stays clean to two decimals.
        self.assertEqual(commission_amount(Decimal("99.99"), Decimal("10")), Decimal("10.00"))


class CommissionTests(TestCase):
    def setUp(self):
        self.broker = User.objects.create_user(
            username="broker_user", email="broker@example.com", password="test12345"
        )
        self.source = User.objects.create_user(
            username="src_user", email="src@example.com", password="test12345"
        )

    def test_create_commission_computes_amount(self):
        commission = create_commission(
            kind="broker_booking",
            recipient=self.broker,
            gross_amount=Decimal("10000"),
            scope="broker",
            source=self.source,
            idempotency_key="booking-1",
        )
        self.assertEqual(commission.amount, Decimal("200.00"))
        self.assertEqual(commission.rate, Decimal("2.00"))
        self.assertEqual(commission.status, Commission.Status.PENDING)
        self.assertEqual(commission.source_type, "users.User")

    def test_create_commission_is_idempotent(self):
        key = "booking-1"
        first = create_commission(
            kind="broker_booking",
            recipient=self.broker,
            gross_amount=Decimal("10000"),
            scope="broker",
            source=self.source,
            idempotency_key=key,
        )
        second = create_commission(
            kind="broker_booking",
            recipient=self.broker,
            gross_amount=Decimal("10000"),
            scope="broker",
            source=self.source,
            idempotency_key=key,
        )
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(Commission.objects.count(), 1)

    def test_cancel_commission(self):
        commission = create_commission(
            kind="broker_booking",
            recipient=self.broker,
            gross_amount=Decimal("10000"),
            scope="broker",
            source=self.source,
            idempotency_key="booking-1",
        )
        from .services.commissions import cancel_commission

        cancel_commission(commission, reason="booking reversed")
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.CANCELED)
        self.assertEqual(commission.detail.get("cancel_reason"), "booking reversed")


class LedgerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ledger_user", email="ledger@example.com", password="test12345"
        )
        self.source = User.objects.create_user(
            username="ledger_src", email="ledger_src@example.com", password="test12345"
        )

    def test_record_entry(self):
        entry = record_entry(
            entry_type="subscription_payment",
            scope="subscription",
            user=self.user,
            gross=Decimal("499.00"),
            platform_amount=Decimal("499.00"),
            partner_amount=0,
            source=self.source,
            idempotency_key="sub-1",
        )
        self.assertEqual(entry.gross_amount, Decimal("499.00"))
        self.assertEqual(entry.platform_amount, Decimal("499.00"))
        self.assertTrue(
            AuditLogEntry.objects.filter(action="revenue.ledger", actor=self.user).exists()
        )

    def test_record_entry_is_idempotent_by_key(self):
        kwargs = dict(
            entry_type="addon_sale",
            scope="marketplace",
            user=self.user,
            gross=Decimal("500"),
            source=self.source,
            idempotency_key="order-1",
        )
        record_entry(**kwargs)
        record_entry(**kwargs)
        self.assertEqual(RevenueLedgerEntry.objects.count(), 1)


class PayoutTests(TestCase):
    def setUp(self):
        self.broker = User.objects.create_user(
            username="payout_broker", email="payout@example.com", password="test12345"
        )
        self.source = User.objects.create_user(
            username="payout_src", email="payout_src@example.com", password="test12345"
        )

    def _earn(self, amount="10000", key="payout-earn-1"):
        return create_commission(
            kind="broker_booking",
            recipient=self.broker,
            gross_amount=Decimal(amount),
            scope="broker",
            source=self.source,
            idempotency_key=key,
        )

    def test_available_balance_is_earned_minus_held(self):
        self._earn("10000", "earn-1")
        self._earn("5000", "earn-2")
        self.assertEqual(available_balance(self.broker), Decimal("300.00"))
        request_payout(user=self.broker, amount=100, method=Payout.Method.BKASH)
        self.assertEqual(available_balance(self.broker), Decimal("200.00"))

    def test_request_payout_creates_pending_with_masked_details(self):
        self._earn()
        payout = request_payout(
            user=self.broker,
            amount=100,
            method=Payout.Method.BKASH,
            account_details={"bkash_number": "01712345678"},
        )
        self.assertEqual(payout.status, Payout.Status.PENDING)
        # Account number is masked — only the last four digits survive.
        self.assertEqual(payout.account_details["bkash_number"], "*******5678")

    def test_request_payout_rejects_bad_amount(self):
        with self.assertRaises(PayoutError):
            request_payout(user=self.broker, amount=0, method=Payout.Method.BKASH)
        with self.assertRaises(PayoutError):
            request_payout(user=self.broker, amount="abc", method=Payout.Method.BKASH)

    def test_request_payout_rejects_over_balance(self):
        self._earn("1000", "small")
        with self.assertRaises(PayoutError):
            request_payout(user=self.broker, amount=1000, method=Payout.Method.BKASH)

    def test_approve_reject_mark_paid_lifecycle(self):
        self._earn()
        payout = request_payout(user=self.broker, amount=100, method=Payout.Method.BKASH)
        admin = User.objects.create_user(
            username="payout_admin", email="pa@example.com", password="test12345", is_staff=True
        )

        from .services.payouts import approve_payout, mark_paid, reject_payout

        with self.assertRaises(PayoutError):
            mark_paid(payout, admin)  # must be approved first

        approve_payout(payout, admin)
        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.APPROVED)
        self.assertEqual(payout.decided_by, admin)

        mark_paid(payout, admin, reference="ref-001")
        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.PAID)
        self.assertEqual(payout.reference, "ref-001")

        rejected = request_payout(user=self.broker, amount=50, method=Payout.Method.BANK)
        reject_payout(rejected, admin, reason="docs missing")
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, Payout.Status.REJECTED)
        self.assertEqual(rejected.reason, "docs missing")


class RevenueDashboardTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="rev_admin", email="rev@example.com", password="test12345", is_staff=True
        )
        self.landlord = User.objects.create_user(
            username="rev_landlord", email="landlord@example.com", password="test12345"
        )
        self.source = User.objects.create_user(
            username="rev_src", email="rev_src@example.com", password="test12345"
        )
        record_entry(
            entry_type="subscription_payment",
            scope="subscription",
            user=self.landlord,
            gross=Decimal("499"),
            platform_amount=Decimal("499"),
            source=self.source,
            idempotency_key="rev-dash-1",
        )
        record_entry(
            entry_type="payout",
            scope="broker",
            user=self.landlord,
            gross=Decimal("0"),
            platform_amount=0,
            partner_amount=0,
            source=self.source,
            idempotency_key="rev-dash-2",
        )

    def test_dashboard_admin_only(self):
        self.client.force_authenticate(self.landlord)
        res = self.client.get("/api/v1/monetization/revenue/dashboard/")
        self.assertEqual(res.status_code, 403)

        self.client.force_authenticate(self.admin)
        res = self.client.get("/api/v1/monetization/revenue/dashboard/")
        self.assertEqual(res.status_code, 200)
        # Payout entries are not recognized platform revenue.
        self.assertEqual(res.data["total_revenue"], Decimal("499"))
