"""Tests for the payments app — booking payments, listing tier promotions."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from rooms.models import Room

from .models import Payment
from .services import bkash
from .views import ListingTierUpgradeInitiateView

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
