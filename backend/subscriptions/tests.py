"""Tests for the subscriptions app — plans, checkout, entitlements, activation.

Money discipline verified here: checkout prices come from the server-side
``Plan.price`` (never the client), and a subscription only activates on the
gateway SUCCESS side-effect — never at initiate time.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from monetization.models import RevenueLedgerEntry
from notifications.models import Notification
from payments.models import Payment
from payments.views import _apply_success_side_effects
from rooms.models import Room

from .models import Plan, Subscription
from .services.entitlements import active_subscription, check_entitlement
from .services.predict import price_prediction_for

User = get_user_model()


def make_room(owner, price=14000, area="Dhanmondi", room_type="single", **kw):
    defaults = dict(
        title="Sub Room",
        description="A test room.",
        room_type=room_type,
        price=price,
        area=area,
        address="Road 6",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi"],
        size_sqft=320,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, **defaults)


class _ThrottleFree(APITestCase):
    """Swap the payment-initiate throttle off for the checkout views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from subscriptions.views import SubscriptionActionView, SubscriptionMeView

        cls._me_throttles = SubscriptionMeView.throttle_classes
        cls._action_throttles = SubscriptionActionView.throttle_classes
        SubscriptionMeView.throttle_classes = []
        SubscriptionActionView.throttle_classes = []

    @classmethod
    def tearDownClass(cls):
        from subscriptions.views import SubscriptionActionView, SubscriptionMeView

        SubscriptionMeView.throttle_classes = cls._me_throttles
        SubscriptionActionView.throttle_classes = cls._action_throttles
        super().tearDownClass()


class PlanCatalogTests(APITestCase):
    def setUp(self):
        self.free = Plan.objects.create(
            code="free",
            name="Free",
            price=0,
            billing_cycle=Plan.BillingCycle.MONTHLY,
            features=["price_prediction_basic"],
        )
        self.pro = Plan.objects.create(
            code="pro",
            name="Pro",
            price=499,
            billing_cycle=Plan.BillingCycle.MONTHLY,
            features=["price_prediction_v2", "analytics_export"],
        )
        Plan.objects.create(
            code="retired",
            name="Retired",
            price=1,
            active=False,
        )

    def test_list_returns_only_active_plans(self):
        res = self.client.get("/api/v1/subscriptions/plans/")
        self.assertEqual(res.status_code, 200)
        codes = {p["code"] for p in res.data["plans"]}
        self.assertIn("free", codes)
        self.assertIn("pro", codes)
        self.assertNotIn("retired", codes)

    def test_plan_price_is_server_side(self):
        res = self.client.get("/api/v1/subscriptions/plans/")
        pro = next(p for p in res.data["plans"] if p["code"] == "pro")
        self.assertEqual(pro["price"], "499.00")


class CheckoutTests(_ThrottleFree):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="sub_landlord", email="sub_landlord@example.com", password="test12345"
        )
        self.plan = Plan.objects.create(
            code="pro",
            name="Pro",
            price=499,
            billing_cycle=Plan.BillingCycle.MONTHLY,
            features=["price_prediction_v2"],
        )

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_checkout_uses_server_price_and_opens_gateway(self, mock_initiate):
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            "/api/v1/subscriptions/subscription/me/",
            {"plan_code": "pro", "method": "sslcommerz"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["payment_url"], "https://gw.example/pay")

        payment = Payment.objects.get()
        self.assertEqual(payment.amount, self.plan.price)
        self.assertEqual(payment.payment_type, Payment.Type.SUBSCRIPTION)
        self.assertEqual(payment.status, Payment.Status.PENDING)

        sub = Subscription.objects.get()
        self.assertEqual(sub.status, Subscription.Status.PENDING)
        self.assertEqual(sub.payment_id, payment.id)
        # The gateway session must not have activated anything yet.
        self.assertIsNone(sub.current_period_end)

    @patch("payments.services.bkash.create_payment")
    def test_checkout_bkash(self, mock_create):
        mock_create.return_value = {"bkashURL": "https://gw.example/bkash"}
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            "/api/v1/subscriptions/subscription/me/",
            {"plan_code": "pro", "method": "bkash"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["bkash_url"], "https://gw.example/bkash")

    def test_duplicate_active_subscription_rejected(self):
        Subscription.objects.create(
            user=self.landlord, plan=self.plan, status=Subscription.Status.PENDING
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            "/api/v1/subscriptions/subscription/me/",
            {"plan_code": "pro", "method": "sslcommerz"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("active subscription", res.data["detail"].lower())

    def test_unknown_plan_404(self):
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            "/api/v1/subscriptions/subscription/me/",
            {"plan_code": "nope", "method": "sslcommerz"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_cancel_pending_subscription(self):
        sub = Subscription.objects.create(
            user=self.landlord, plan=self.plan, status=Subscription.Status.PENDING
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            f"/api/v1/subscriptions/subscription/{sub.pk}/cancel/?action=cancel",
            {},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_renew_creates_payment(self, mock_initiate):
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        sub = Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=10),
        )
        self.client.force_authenticate(self.landlord)
        res = self.client.post(
            f"/api/v1/subscriptions/subscription/{sub.pk}/renew/?action=renew",
            {"method": "sslcommerz"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Payment.objects.count(), 1)
        # Initiate alone must not extend the period.
        sub.refresh_from_db()
        self.assertLess(sub.current_period_end - timezone.now(), timedelta(days=11))


class ActivationTests(APITestCase):
    """The gateway SUCCESS callback — where subscriptions actually activate."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="activate_landlord", email="activate@example.com", password="test12345"
        )
        self.plan = Plan.objects.create(
            code="pro",
            name="Pro",
            price=499,
            billing_cycle=Plan.BillingCycle.MONTHLY,
            features=["price_prediction_v2"],
        )

    def _payment_for(self, sub):
        payment = Payment.objects.create(
            user=self.landlord,
            amount=self.plan.price,
            payment_type=Payment.Type.SUBSCRIPTION,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.INITIATED,
            subscription=sub,
        )
        sub.payment = payment
        sub.save(update_fields=["payment"])
        return payment

    def test_activation_on_success(self):
        sub = Subscription.objects.create(
            user=self.landlord, plan=self.plan, status=Subscription.Status.PENDING
        )
        payment = self._payment_for(sub)
        payment.gateway_response = {"validated": True}
        payment.transition_status(Payment.Status.SUCCESS)
        _apply_success_side_effects(payment)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(sub.current_period_start)
        self.assertGreater(sub.current_period_end, timezone.now() + timedelta(days=29))
        self.assertFalse(sub.cancel_at_period_end)

        # One revenue ledger entry for the platform.
        entry = RevenueLedgerEntry.objects.get(entry_type="subscription_payment")
        self.assertEqual(entry.gross_amount, self.plan.price)
        self.assertEqual(entry.platform_amount, self.plan.price)

        # The tenant/landlord got notified.
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord,
                notification_type=Notification.Type.SUBSCRIPTION_ACTIVE,
            ).exists()
        )

    def test_renewal_extends_period_from_current_end(self):
        original_end = timezone.now() + timedelta(days=10)
        sub = Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=original_end,
        )
        payment = self._payment_for(sub)
        payment.transition_status(Payment.Status.SUCCESS)
        _apply_success_side_effects(payment)

        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertAlmostEqual((sub.current_period_end - original_end).days, 30, delta=1)
        self.assertTrue(
            RevenueLedgerEntry.objects.filter(entry_type="subscription_renewal").exists()
        )

    def test_payment_without_subscription_is_a_noop(self):
        """Booking/promotion payments must never touch the subscription flow."""
        payment = Payment.objects.create(
            user=self.landlord,
            amount=100,
            payment_type=Payment.Type.LISTING_FEATURE,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.INITIATED,
        )
        payment.transition_status(Payment.Status.SUCCESS)
        _apply_success_side_effects(payment)  # room is None → early return
        self.assertEqual(Subscription.objects.count(), 0)


class EntitlementTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ent_landlord", email="ent@example.com", password="test12345"
        )
        self.room = make_room(self.landlord)
        self.plan = Plan.objects.create(
            code="pro",
            name="Pro",
            price=499,
            features=["price_prediction_v2"],
        )

    def test_free_features_open_without_subscription(self):
        self.assertTrue(check_entitlement(self.landlord, "price_prediction_basic"))
        self.assertFalse(check_entitlement(self.landlord, "price_prediction_v2"))

    def test_plan_grants_premium_feature(self):
        Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        self.assertTrue(check_entitlement(self.landlord, "price_prediction_v2"))

    def test_expired_subscription_grants_nothing_premium(self):
        Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.EXPIRED,
            current_period_start=timezone.now() - timedelta(days=60),
            current_period_end=timezone.now() - timedelta(days=30),
        )
        self.assertFalse(check_entitlement(self.landlord, "price_prediction_v2"))

    def test_active_subscription_is_unique(self):
        active = Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        self.assertEqual(active_subscription(self.landlord).pk, active.pk)

    def test_free_prediction_is_stripped_backward_compatible(self):
        out = price_prediction_for(self.landlord, self.room)
        self.assertEqual(out["room_id"], self.room.pk)
        self.assertFalse(out["premium_unlocked"])
        self.assertIsNone(out["plan"])
        self.assertNotIn("dynamic_price", out)
        self.assertNotIn("valid_until", out)

    def test_premium_prediction_unlocks_v2(self):
        Subscription.objects.create(
            user=self.landlord,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        out = price_prediction_for(self.landlord, self.room)
        self.assertTrue(out["premium_unlocked"])
        self.assertEqual(out["plan"], "pro")
        self.assertIn("dynamic_price", out)
        self.assertIn("valid_until", out)
