"""Tests for the payments app — booking payments, listing tier promotions."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking
from notifications.models import Notification
from rooms.models import Room

from .models import Invoice, Payment, PaymentAuditLog, PaymentSchedule
from .services import bkash
from .services.invoice import generate_invoice_pdf, get_or_create_invoice_for_payment
from .services.reminders import send_payment_reminders
from .services.schedule import generate_payment_schedule
from .views import (
    BkashCallbackView,
    BkashInitiateView,
    ListingTierUpgradeInitiateView,
    PaymentCancelCallbackView,
    PaymentFailCallbackView,
    PaymentInitiateView,
    PaymentSuccessCallbackView,
)

User = get_user_model()


class ListingTierUpgradeTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The initiate view throttles at 5/hour per user — tests hit it far
        # more often, so swap the throttle off for the class and restore it.
        cls._saved_throttles = ListingTierUpgradeInitiateView.throttle_classes
        ListingTierUpgradeInitiateView.throttle_classes = []

    @classmethod
    def tearDownClass(cls):
        ListingTierUpgradeInitiateView.throttle_classes = cls._saved_throttles
        super().tearDownClass()

    """The paid-listing promotion flow: initiate -> gateway -> activate tier."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="promoter", email="p@example.com", password="pw12345!"
        )
        cls.other = User.objects.create_user(
            username="someoneelse", email="o@example.com", password="pw12345!"
        )
        cls.room = Room.objects.create(
            title="Promotable Room",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="somewhere",
            lat=23.74,
            lng=90.37,
            size_sqft=200,
            owner=cls.owner,
            tier=Room.Tier.FREE,
        )

    def _initiate(self, tier="featured", method="sslcommerz", user=None):
        self.client.force_authenticate(user or self.owner)
        return self.client.post(
            "/api/v1/payments/tier-upgrade/initiate/",
            {"room_id": self.room.id, "tier": tier, "method": method},
            format="json",
        )

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_initiate_creates_payment_with_server_price(self, mock_initiate):
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        res = self._initiate()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["payment_url"], "https://gw.example/pay")

        payment = Payment.objects.get()
        self.assertIsNone(payment.booking)
        self.assertEqual(payment.room_id, self.room.id)
        # Price comes from settings, never the client.
        self.assertEqual(payment.amount, settings.LISTING_TIER_PRICING["featured"])
        self.assertEqual(payment.payment_type, Payment.Type.LISTING_FEATURE)

    @patch("payments.services.bkash.create_payment")
    def test_initiate_bkash(self, mock_create):
        mock_create.return_value = {"bkashURL": "https://gw.example/bkash"}
        res = self._initiate(tier="premium", method="bkash")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["bkash_url"], "https://gw.example/bkash")
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, settings.LISTING_TIER_PRICING["premium"])
        self.assertEqual(payment.payment_type, Payment.Type.LISTING_PREMIUM)

    def test_non_owner_cannot_promote(self):
        res = self._initiate(user=self.other)
        self.assertEqual(res.status_code, 403)

    def test_unknown_room_404(self):
        self.client.force_authenticate(self.owner)
        res = self.client.post(
            "/api/v1/payments/tier-upgrade/initiate/",
            {"room_id": 99999, "tier": "featured"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_invalid_tier_400(self):
        res = self._initiate(tier="ultra")
        self.assertEqual(res.status_code, 400)

    def test_duplicate_active_tier_rejected(self):
        self.room.tier = Room.Tier.FEATURED
        self.room.tier_expires_at = timezone.now() + timedelta(days=10)
        self.room.save()
        res = self._initiate(tier="featured")
        self.assertEqual(res.status_code, 400)
        self.assertIn("already", res.data["detail"].lower())

    def test_downgrade_rejected(self):
        """A Premium listing can't pay to drop itself to Featured."""
        self.room.tier = Room.Tier.PREMIUM
        self.room.tier_expires_at = timezone.now() + timedelta(days=10)
        self.room.save()
        res = self._initiate(tier="featured")
        self.assertEqual(res.status_code, 400)
        self.assertIn("higher tier", res.data["detail"].lower())

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_success_activates_tier_and_side_effects(self, mock_initiate):
        """The callback side-effect — not the initiate — grants the tier."""
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        res = self._initiate(tier="premium")
        self.assertEqual(res.status_code, 201)
        payment = Payment.objects.get()

        self.assertNotEqual(self.room.tier, Room.Tier.PREMIUM)  # not yet granted

        # Simulate the success callback settling the payment.
        payment.gateway_response = {"validated": True}
        payment.transition_status(Payment.Status.SUCCESS)
        from payments.views import _apply_success_side_effects

        _apply_success_side_effects(payment)

        self.room.refresh_from_db()
        self.assertEqual(self.room.tier, Room.Tier.PREMIUM)
        self.assertTrue(self.room.is_featured)
        self.assertIsNotNone(self.room.tier_expires_at)
        self.assertGreater(
            self.room.tier_expires_at,
            timezone.now() + timedelta(days=settings.LISTING_TIER_DURATION_DAYS - 1),
        )

    def test_receipt_guards_tier_payment(self):
        """Receipts work for promotion payments (room, no booking)."""
        payment = Payment.objects.create(
            room=self.room,
            booking=None,
            user=self.owner,
            amount=settings.LISTING_TIER_PRICING["featured"],
            payment_type=Payment.Type.LISTING_FEATURE,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.SUCCESS,
        )
        from payments.services.receipt import generate_receipt_pdf

        pdf = generate_receipt_pdf(payment)
        self.assertTrue(pdf.startswith(b"%PDF"))


class BkashGrantTokenTests(TestCase):
    """Phase 16 — grant-token cache + single-flight lock (no stampede)."""

    def _fake_post(self, token="tok-1", expires_in=3600):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"id_token": token, "expires_in": expires_in}

        return FakeResponse()

    def setUp(self):
        cache.clear()

    def test_token_is_cached(self):
        with patch.object(bkash.requests, "post", return_value=self._fake_post()) as mock:
            first = bkash.get_grant_token()
            second = bkash.get_grant_token()
        self.assertEqual(first, "tok-1")
        self.assertEqual(second, "tok-1")
        # One upstream grant, two local reads.
        self.assertEqual(mock.call_count, 1)

    def test_force_refresh_always_grants(self):
        with patch.object(
            bkash.requests, "post", side_effect=[self._fake_post(), self._fake_post()]
        ) as mock:
            bkash.get_grant_token()
            bkash.get_grant_token(force_refresh=True)
        self.assertEqual(mock.call_count, 2)

    def test_single_flight_lock_allows_waiting_caller_to_read_cache(self):
        """The lock winner grants; a loser re-reads the cache instead of re-granting."""
        with patch.object(bkash.requests, "post", return_value=self._fake_post()):
            bkash.get_grant_token()  # populate cache
        cache.delete(bkash.GRANT_TOKEN_CACHE_KEY)
        cache.set(bkash.GRANT_TOKEN_LOCK_KEY, "held-by-other", timeout=10)
        with patch.object(bkash.requests, "post", return_value=self._fake_post("tok-2")) as mock2:
            token = bkash.get_grant_token()
        # Lock held → loser reads cache (empty) → falls through to a direct grant.
        self.assertEqual(token, "tok-2")
        self.assertEqual(mock2.call_count, 1)

    def test_lock_is_released_after_grant(self):
        with patch.object(bkash.requests, "post", return_value=self._fake_post()):
            bkash.get_grant_token()
        self.assertIsNone(cache.get(bkash.GRANT_TOKEN_LOCK_KEY))


# ---------------------------------------------------------------------------
# Booking payment flow — the money path: initiate → gateway callback → schedule
# linking → deposit bookkeeping → invoice → reminder → refund.
# ---------------------------------------------------------------------------


class _ThrottleOffMixin:
    """Turn the payment throttles off for a test class and restore them after.

    The initiate views allow 5/hour and the callback views 20/minute per IP —
    far fewer than a test run performs — so they're swapped off for the
    duration, matching the existing ``ListingTierUpgradeTests`` pattern.
    """

    views_to_unthrottle: tuple = ()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._saved_throttles = {v: v.throttle_classes for v in cls.views_to_unthrottle}
        for view in cls.views_to_unthrottle:
            view.throttle_classes = []

    @classmethod
    def tearDownClass(cls):
        for view in cls.views_to_unthrottle:
            view.throttle_classes = cls._saved_throttles[view]
        super().tearDownClass()


class BookingPaymentFixturesMixin:
    """Share landlord/tenant/room/approved-booking fixtures across money tests."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="pl",
            email="pl@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
        )
        self.tenant = User.objects.create_user(
            username="pt",
            email="pt@example.com",
            password="test12345",
            role=User.Role.TENANT,
        )
        self.other = User.objects.create_user(
            username="po", email="po@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Payable Room",
            description="test",
            room_type=Room.RoomType.SINGLE,
            price=8000,
            area=Room.Area.DHANMONDI,
            address="somewhere",
            lat=23.74,
            lng=90.37,
            size_sqft=200,
        )
        self.booking = Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 15),
            check_out=date(2026, 4, 1),
            monthly_rent=8000,
            security_deposit_amount=5000,
        )
        generate_payment_schedule(self.booking)

    def _make_payment(self, **overrides):
        defaults = {
            "booking": self.booking,
            "user": self.tenant,
            "amount": self.booking.monthly_rent,
            "payment_type": Payment.Type.MONTHLY_RENT,
            "payment_method": Payment.Method.SSLCOMMERZ,
            "status": Payment.Status.INITIATED,
        }
        defaults.update(overrides)
        return Payment.objects.create(**defaults)


class BookingPaymentInitiateTests(_ThrottleOffMixin, BookingPaymentFixturesMixin, APITestCase):
    views_to_unthrottle = (PaymentInitiateView, BkashInitiateView)

    def _initiate(self, **overrides):
        payload = {
            "booking_id": self.booking.pk,
            "payment_type": Payment.Type.MONTHLY_RENT,
            **overrides,
        }
        return self.client.post("/api/v1/payments/initiate/", payload, format="json")

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_sslcommerz_initiate_for_approved_booking(self, mock_initiate):
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        self.client.force_authenticate(self.tenant)
        res = self._initiate()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["payment_url"], "https://gw.example/pay")

        payment = Payment.objects.get()
        self.assertEqual(payment.booking_id, self.booking.pk)
        self.assertEqual(payment.user_id, self.tenant.id)
        # Amount is the server-side booking rent — never taken from the client,
        # and a tampered "amount" body field is silently ignored.
        self.assertEqual(res.data["transaction_id"], payment.transaction_id)
        self.assertEqual(payment.amount, self.booking.monthly_rent)
        self.assertEqual(payment.payment_method, Payment.Method.SSLCOMMERZ)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        # The initiate → pending move leaves an audit trail.
        self.assertEqual(payment.audit_logs.count(), 1)

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_client_cannot_set_amount(self, mock_initiate):
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        self.client.force_authenticate(self.tenant)
        res = self._initiate(amount=1, payment_method="bkash", method="does-not-matter")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(Payment.objects.get().amount, self.booking.monthly_rent)

    @patch("payments.services.bkash.create_payment")
    def test_bkash_initiate(self, mock_create):
        mock_create.return_value = {"bkashURL": "https://gw.example/bkash"}
        self.client.force_authenticate(self.tenant)
        res = self.client.post(
            "/api/v1/payments/bkash/initiate/",
            {"booking_id": self.booking.pk, "payment_type": Payment.Type.MONTHLY_RENT},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["bkash_url"], "https://gw.example/bkash")
        payment = Payment.objects.get()
        self.assertEqual(payment.payment_method, Payment.Method.BKASH)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        # The callback URL carries our own transaction_id for identification.
        self.assertIn(payment.transaction_id, mock_create.call_args[0][1])

    def test_cannot_initiate_for_non_approved_booking(self):
        self.booking.status = Booking.Status.PENDING
        self.booking.save(update_fields=["status"])
        self.client.force_authenticate(self.tenant)
        res = self._initiate()
        self.assertEqual(res.status_code, 400)
        self.assertIn("approved", str(res.data).lower())

    def test_cannot_initiate_for_someone_elses_booking(self):
        self.client.force_authenticate(self.other)
        res = self._initiate()
        self.assertEqual(res.status_code, 400)
        self.assertIn("own bookings", str(res.data).lower())

    @patch("payments.services.sslcommerz.initiate_payment", side_effect=Exception("boom"))
    def test_gateway_failure_marks_payment_failed(self, mock_initiate):
        from payments.services.sslcommerz import SSLCommerzError

        mock_initiate.side_effect = SSLCommerzError("Could not reach SSLCommerz")
        self.client.force_authenticate(self.tenant)
        res = self._initiate()
        self.assertEqual(res.status_code, 502)
        payment = Payment.objects.get()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("Could not reach", payment.failure_reason)


class PaymentCallbackTests(_ThrottleOffMixin, BookingPaymentFixturesMixin, APITestCase):
    """Only a genuinely validated gateway callback settles a payment."""

    views_to_unthrottle = (
        PaymentSuccessCallbackView,
        PaymentFailCallbackView,
        PaymentCancelCallbackView,
        BkashCallbackView,
    )

    def test_sslcommerz_success_settles_payment(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "VALID", "amount": str(payment.amount), "val_id": "VAL-1"},
        ) as mock_validate:
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "VAL-1"},
                format="json",
            )
        mock_validate.assert_called_once_with("VAL-1")
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=success", res.url)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.gateway_transaction_id, "VAL-1")
        self.assertTrue(
            PaymentAuditLog.objects.filter(payment=payment, new_status="success").exists()
        )
        # Both the tenant and the landlord are told about the money arriving.
        self.assertTrue(
            self.tenant.notifications.filter(
                notification_type=Notification.Type.PAYMENT_SUCCESS
            ).exists()
        )
        self.assertTrue(
            self.landlord.notifications.filter(
                notification_type=Notification.Type.PAYMENT_SUCCESS
            ).exists()
        )

    def test_sslcommerz_success_marks_security_deposit_paid(self):
        """The deposit flow: a settled SECURITY_DEPOSIT payment unlocks approval."""
        payment = self._make_payment(
            payment_type=Payment.Type.SECURITY_DEPOSIT,
            amount=5000,
            status=Payment.Status.PENDING,
        )
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "VALID", "amount": "5000.00", "val_id": "VAL-D"},
        ):
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "VAL-D"},
                format="json",
            )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=success", res.url)
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.security_deposit_paid)

    def test_sslcommerz_success_links_monthly_rent_to_schedule(self):
        """A settled monthly-rent payment clears the oldest unpaid installment."""
        payment = self._make_payment(status=Payment.Status.PENDING)
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "VALID", "amount": str(payment.amount), "val_id": "VAL-R"},
        ):
            self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "VAL-R"},
                format="json",
            )
        schedule_entry = self.booking.payment_schedules.get(payment=payment)
        self.assertEqual(schedule_entry.status, PaymentSchedule.Status.PAID)

    def test_amount_mismatch_fails_payment(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "VALID", "amount": "1.00", "val_id": "VAL-1"},
        ):
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "VAL-1"},
                format="json",
            )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=fail", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn("Amount mismatch", payment.failure_reason)
        self.assertFalse(self.booking.security_deposit_paid)

    def test_invalid_gateway_validation_fails_payment(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "INVALID"},
        ):
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "FORGED"},
                format="json",
            )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=fail", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(payment.amount, self.booking.monthly_rent)  # nothing granted

    def test_fail_callback_marks_payment_failed(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        res = self.client.post(
            "/api/v1/payments/sslcommerz/fail/",
            {"tran_id": payment.transaction_id},
            format="json",
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=fail", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertTrue(
            PaymentAuditLog.objects.filter(payment=payment, new_status="failed").exists()
        )

    def test_cancel_callback_marks_payment_cancelled(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        res = self.client.post(
            "/api/v1/payments/sslcommerz/cancel/",
            {"tran_id": payment.transaction_id},
            format="json",
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=cancel", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)

    def test_terminal_payment_cannot_be_reflipped(self):
        """Once settled (success), a forged/cancelled retry must not mutate it."""
        payment = self._make_payment(status=Payment.Status.SUCCESS)
        res = self.client.post(
            "/api/v1/payments/sslcommerz/cancel/",
            {"tran_id": payment.transaction_id},
            format="json",
        )
        self.assertEqual(res.status_code, 302)
        # Redirect reflects what actually happened — success, not the forged cancel.
        self.assertIn("status=success", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_bkash_callback_settles_payment(self):
        payment = self._make_payment(
            payment_method=Payment.Method.BKASH, status=Payment.Status.PENDING
        )
        with (
            patch(
                "payments.services.bkash.query_payment",
                return_value={"transactionStatus": "Completed"},
            ),
            patch(
                "payments.services.bkash.execute_payment",
                return_value={
                    "transactionStatus": "Completed",
                    "amount": str(payment.amount),
                    "trxID": "TRX-1",
                },
            ) as mock_execute,
        ):
            res = self.client.get(
                f"/api/v1/payments/bkash/callback/?tran_id={payment.transaction_id}&paymentID=PAY-1"
            )
        mock_execute.assert_called_once_with("PAY-1")
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=success", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.gateway_transaction_id, "TRX-1")

    def test_bkash_amount_mismatch_fails_payment(self):
        payment = self._make_payment(
            payment_method=Payment.Method.BKASH, status=Payment.Status.PENDING
        )
        with (
            patch(
                "payments.services.bkash.query_payment",
                return_value={"transactionStatus": "Completed"},
            ),
            patch(
                "payments.services.bkash.execute_payment",
                return_value={
                    "transactionStatus": "Completed",
                    "amount": "1.00",
                    "trxID": "TRX-1",
                },
            ),
        ):
            res = self.client.get(
                f"/api/v1/payments/bkash/callback/?tran_id={payment.transaction_id}&paymentID=PAY-1"
            )
        self.assertEqual(res.status_code, 302)
        self.assertIn("status=fail", res.url)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)


class PaymentHistoryTests(_ThrottleOffMixin, BookingPaymentFixturesMixin, APITestCase):
    def test_history_scoped_to_paying_user(self):
        payment = self._make_payment(status=Payment.Status.SUCCESS)
        self.client.force_authenticate(self.tenant)
        res = self.client.get("/api/v1/payments/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["transaction_id"], payment.transaction_id)

        self.client.force_authenticate(self.landlord)
        res = self.client.get("/api/v1/payments/")
        self.assertEqual(res.data["count"], 0)

    def test_summary_totals(self):
        self._make_payment(status=Payment.Status.SUCCESS, amount=8000)
        self._make_payment(status=Payment.Status.INITIATED, amount=8000)
        self.client.force_authenticate(self.tenant)
        res = self.client.get("/api/v1/payments/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_paid"], 8000.0)
        self.assertEqual(res.data["count_paid"], 1)
        self.assertEqual(res.data["total_pending"], 8000.0)


class PaymentReceiptAndInvoiceTests(_ThrottleOffMixin, BookingPaymentFixturesMixin, APITestCase):
    def test_receipt_only_for_successful_payment(self):
        payment = self._make_payment(status=Payment.Status.PENDING)
        self.client.force_authenticate(self.tenant)
        res = self.client.get(f"/api/v1/payments/{payment.pk}/receipt/")
        self.assertEqual(res.status_code, 400)

        payment.transition_status(Payment.Status.SUCCESS)
        res = self.client.get(f"/api/v1/payments/{payment.pk}/receipt/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))

    def test_invoice_generated_for_booking_payment(self):
        payment = self._make_payment(status=Payment.Status.SUCCESS)
        self.client.force_authenticate(self.tenant)
        res = self.client.get(f"/api/v1/payments/{payment.pk}/invoice/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(res.content.startswith(b"%PDF"))
        # An invoice row was allocated and marked paid.
        payment.refresh_from_db()
        self.assertEqual(payment.invoice.status, Invoice.Status.PAID)

    def test_invoice_available_to_landlord_too(self):
        payment = self._make_payment(status=Payment.Status.SUCCESS)
        self.client.force_authenticate(self.landlord)
        res = self.client.get(f"/api/v1/payments/{payment.pk}/invoice/")
        self.assertEqual(res.status_code, 200)

    def test_invoice_denied_to_unrelated_user(self):
        payment = self._make_payment(status=Payment.Status.SUCCESS)
        self.client.force_authenticate(self.other)
        res = self.client.get(f"/api/v1/payments/{payment.pk}/invoice/")
        self.assertEqual(res.status_code, 403)

    def test_listing_promotion_has_no_invoice(self):
        promotion = Payment.objects.create(
            room=self.room,
            booking=None,
            user=self.landlord,
            amount=settings.LISTING_TIER_PRICING["featured"],
            payment_type=Payment.Type.LISTING_FEATURE,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.SUCCESS,
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.get(f"/api/v1/payments/{promotion.pk}/invoice/")
        self.assertEqual(res.status_code, 400)


class PaymentInvoiceServiceTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="isl", email="isl@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="ist", email="ist@example.com", password="test12345"
        )
        room = Room.objects.create(
            owner=self.landlord,
            title="Invoice Room",
            description="d",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            size_sqft=200,
        )
        self.booking = Booking.objects.create(
            room=room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=date(2026, 1, 15),
            check_out=date(2026, 4, 1),
            monthly_rent=8000,
        )
        self.payment = Payment.objects.create(
            booking=self.booking,
            user=self.tenant,
            amount=8000,
            payment_type=Payment.Type.MONTHLY_RENT,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.SUCCESS,
        )

    def test_invoice_is_created_once_and_idempotent(self):
        inv1 = get_or_create_invoice_for_payment(self.payment)
        inv2 = get_or_create_invoice_for_payment(self.payment)
        self.assertEqual(inv1.pk, inv2.pk)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_invoice_number_is_sequential(self):
        year = timezone.now().year
        inv1 = get_or_create_invoice_for_payment(self.payment)
        self.assertEqual(inv1.invoice_number, f"INV-{year}-0001")
        second = Payment.objects.create(
            booking=self.booking,
            user=self.tenant,
            amount=8000,
            payment_type=Payment.Type.MONTHLY_RENT,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.SUCCESS,
        )
        inv2 = get_or_create_invoice_for_payment(second)
        self.assertEqual(inv2.invoice_number, f"INV-{year}-0002")

    def test_invoice_status_follows_payment_without_downgrading_paid(self):
        inv = get_or_create_invoice_for_payment(self.payment)
        self.assertEqual(inv.status, Invoice.Status.PAID)
        # A later transition (e.g. refund) never downgrades the invoice.
        self.payment.transition_status(Payment.Status.REFUNDED)
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.Status.PAID)

    def test_pending_payment_invoice_is_sent(self):
        pending = Payment.objects.create(
            booking=self.booking,
            user=self.tenant,
            amount=8000,
            payment_type=Payment.Type.MONTHLY_RENT,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.PENDING,
        )
        inv = get_or_create_invoice_for_payment(pending)
        self.assertEqual(inv.status, Invoice.Status.SENT)

    def test_invoice_pdf_renders(self):
        pdf = generate_invoice_pdf(self.payment)
        self.assertTrue(pdf.startswith(b"%PDF"))


class PaymentRefundTests(_ThrottleOffMixin, BookingPaymentFixturesMixin, APITestCase):
    def _settled_deposit_payment(self):
        return self._make_payment(
            payment_type=Payment.Type.SECURITY_DEPOSIT,
            amount=5000,
            gateway_transaction_id="BANK-1",
            status=Payment.Status.SUCCESS,
        )

    @patch("payments.services.sslcommerz.refund_payment", return_value={"status": "success"})
    def test_landlord_refunds_security_deposit(self, mock_refund):
        payment = self._settled_deposit_payment()
        self.client.force_authenticate(self.landlord)
        res = self.client.post(f"/api/v1/payments/{payment.pk}/refund/", {}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        self.assertIn("refund", payment.gateway_response)
        self.assertTrue("refund_amount" in payment.audit_logs.latest("created_at").metadata)
        # The deposit cycle on the booking is closed.
        self.booking.refresh_from_db()
        self.assertTrue(self.booking.security_deposit_refunded)

    def test_tenant_cannot_refund(self):
        payment = self._settled_deposit_payment()
        self.client.force_authenticate(self.tenant)
        res = self.client.post(f"/api/v1/payments/{payment.pk}/refund/", {}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_cannot_refund_unsettled_payment(self):
        payment = self._make_payment(
            payment_type=Payment.Type.SECURITY_DEPOSIT, amount=5000, status=Payment.Status.PENDING
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(f"/api/v1/payments/{payment.pk}/refund/", {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("successful", str(res.data).lower())

    def test_refund_amount_is_capped(self):
        payment = self._settled_deposit_payment()
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            f"/api/v1/payments/{payment.pk}/refund/", {"amount": 999999}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_manual_payments_cannot_be_refunded_through_gateway(self):
        payment = self._make_payment(
            payment_type=Payment.Type.MONTHLY_RENT,
            payment_method=Payment.Method.MANUAL,
            status=Payment.Status.SUCCESS,
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(f"/api/v1/payments/{payment.pk}/refund/", {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("not supported", str(res.data).lower())


class PaymentScheduleTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ssl", email="ssl@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="sst", email="sst@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Schedule Room",
            description="d",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            size_sqft=200,
        )

    def _booking(self, check_in, check_out=None):
        return Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=Booking.Status.APPROVED,
            check_in=check_in,
            check_out=check_out,
            monthly_rent=8000,
        )

    def test_open_ended_lease_gets_default_lease_months(self):
        booking = self._booking(date(2026, 1, 15))
        entries = generate_payment_schedule(booking)
        self.assertEqual(len(entries), settings.DEFAULT_LEASE_SCHEDULE_MONTHS)
        self.assertEqual(entries[0].due_date, date(2026, 1, 15))
        self.assertEqual([e.amount for e in entries], [8000] * len(entries))
        self.assertEqual({e.status for e in entries}, {PaymentSchedule.Status.UPCOMING})

    def test_fixed_checkout_generates_installments_until_end(self):
        booking = self._booking(date(2026, 1, 15), date(2026, 4, 1))
        entries = generate_payment_schedule(booking)
        self.assertEqual(
            [e.due_date for e in entries], [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
        )

    def test_short_month_due_dates_are_clamped(self):
        booking = self._booking(date(2026, 1, 31))
        entries = generate_payment_schedule(booking)
        self.assertEqual(entries[0].due_date, date(2026, 1, 31))
        self.assertEqual(entries[1].due_date, date(2026, 2, 28))  # Feb clamped

    def test_generation_is_idempotent(self):
        booking = self._booking(date(2026, 1, 15), date(2026, 4, 1))
        generate_payment_schedule(booking)
        second = generate_payment_schedule(booking)
        self.assertEqual(second, [])
        self.assertEqual(booking.payment_schedules.count(), 3)


class PaymentReminderTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="rll", email="rll@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="rtt", email="rtt@example.com", password="test12345"
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Reminder Room",
            description="d",
            room_type="single",
            price=8000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            size_sqft=200,
        )

    def _booking(self, check_in, status=Booking.Status.APPROVED):
        return Booking.objects.create(
            room=self.room,
            tenant=self.tenant,
            status=status,
            check_in=check_in,
            monthly_rent=8000,
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 3, 12))
    def test_reminder_sent_when_rent_due_in_3_days(self, mock_today):
        self._booking(date(2026, 2, 15))  # next due 2026-03-15 == today + 3
        result = send_payment_reminders()
        self.assertEqual(result, {"sent": 1, "due_date": "2026-03-15"})
        notif = self.tenant.notifications.get(notification_type=Notification.Type.PAYMENT_REMINDER)
        self.assertIn("due in 3 days", notif.message)

    @patch(
        "django.utils.timezone.now", return_value=timezone.make_aware(datetime(2026, 3, 12, 10, 0))
    )
    @patch("django.utils.timezone.localdate", return_value=date(2026, 3, 12))
    def test_reminder_is_idempotent_per_day(self, mock_today, mock_now):
        self._booking(date(2026, 2, 15))
        send_payment_reminders()
        second = send_payment_reminders()
        self.assertEqual(second["sent"], 0)
        self.assertEqual(
            self.tenant.notifications.filter(
                notification_type=Notification.Type.PAYMENT_REMINDER
            ).count(),
            1,
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 3, 12))
    def test_no_reminder_when_rent_not_due(self, mock_today):
        self._booking(date(2026, 1, 15))  # next due 2026-02-15 ≠ today + 3
        result = send_payment_reminders()
        self.assertEqual(result["sent"], 0)

    @patch("django.utils.timezone.localdate", return_value=date(2026, 3, 12))
    def test_only_approved_bookings_are_reminded(self, mock_today):
        self._booking(date(2026, 2, 15), status=Booking.Status.PENDING)
        result = send_payment_reminders()
        self.assertEqual(result["sent"], 0)

    @patch("django.utils.timezone.localdate", return_value=date(2026, 3, 12))
    def test_reminder_based_on_last_payment_not_original_checkin(self, mock_today):
        booking = self._booking(date(2020, 1, 15))
        # The tenant already paid through 2026-02-15, so the next installment
        # falls on 2026-03-15 — the original (2020) check-in is irrelevant.
        last_payment = Payment.objects.create(
            booking=booking,
            user=self.tenant,
            amount=8000,
            payment_type=Payment.Type.MONTHLY_RENT,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.SUCCESS,
        )
        Payment.objects.filter(pk=last_payment.pk).update(
            created_at=timezone.make_aware(datetime(2026, 2, 15, 12, 0))
        )
        result = send_payment_reminders()
        self.assertEqual(result["sent"], 1)
