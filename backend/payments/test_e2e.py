"""E2E: the paid-listing promotion lifecycle through the real API.

One continuous story across the whole stack, exactly as a landlord's browser
would drive it (only the two external gateway HTTP calls are mocked):

1. Landlord publishes a room (``POST /rooms/``) → free tier.
2. Landlord initiates a Featured upgrade (``POST /payments/tier-upgrade/initiate/``)
   → payment PENDING at the *server-side* price (a tampered client can't set it).
3. The gateway's success callback (``POST /payments/sslcommerz/success/``)
   settles the payment → room becomes Featured for LISTING_TIER_DURATION_DAYS,
   the landlord gets the "Listing promoted" notification, and a payment audit
   entry is written.
4. Scheduled expiry (``expire_listing_tiers``) reverts the room to Free and
   emails the owner the ``promotion_expired`` template.

A second test covers the Premium path through the bKash callback (query +
execute), so both gateways' callbacks are exercised end-to-end.

This is the money-flow contract: a tier is ONLY ever granted by a settled
payment callback — never at initiate, never by client input.
"""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import tag
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import Notification
from payments.models import Payment, PaymentAuditLog
from rooms.models import Room
from rooms.services import expire_listing_tiers

from .views import BkashCallbackView, ListingTierUpgradeInitiateView, PaymentSuccessCallbackView

User = get_user_model()

# NOTE: the callback tests silently rely on the empty ``*_WEBHOOK_IP_ALLOWLIST``
# + sandbox defaults (see payments/services/webhook_security.py): with no
# allowlist configured, ``check_webhook_ip`` accepts any source IP. If CI or
# production ever configures real gateway IP ranges here, these tests must be
# updated to override those settings.

# Views whose throttles would trip a test run (5/hour initiate, 20/min
# callbacks per IP) — disabled for the class, restored afterwards, matching
# the existing ListingTierUpgradeTests pattern.
_THROTTLED_VIEWS = (ListingTierUpgradeInitiateView, PaymentSuccessCallbackView, BkashCallbackView)


@tag("e2e")
class ListingPromotionE2ETest(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._saved_throttles = {v: v.throttle_classes for v in _THROTTLED_VIEWS}
        for view in _THROTTLED_VIEWS:
            view.throttle_classes = []

    @classmethod
    def tearDownClass(cls):
        for view in _THROTTLED_VIEWS:
            view.throttle_classes = cls._saved_throttles[view]
        super().tearDownClass()

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="landlord",
            email="landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=True,
        )

    def _publish_room(self, title="Promotable Studio"):
        self.client.force_authenticate(user=self.landlord)
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": title,
                "description": "A bright, well-written studio listing.",
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
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return Room.objects.get(pk=res.data["id"])

    def _initiate(self, room, tier, method="sslcommerz"):
        self.client.force_authenticate(user=self.landlord)
        return self.client.post(
            "/api/v1/payments/tier-upgrade/initiate/",
            {"room_id": room.pk, "tier": tier, "method": method},
            format="json",
        )

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_full_promotion_lifecycle(self, mock_initiate):
        """Publish → initiate → SSLCommerz callback → Featured → expiry → Free + email."""
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        room = self._publish_room()
        self.assertEqual(room.tier, Room.Tier.FREE)

        # 1. Initiate the Featured upgrade. Amount is server-side; nothing
        #    is granted yet.
        res = self._initiate(room, "featured")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["payment_url"], "https://gw.example/pay")
        payment = Payment.objects.get(transaction_id=res.data["transaction_id"])
        self.assertEqual(payment.payment_type, Payment.Type.LISTING_FEATURE)
        self.assertEqual(payment.amount, settings.LISTING_TIER_PRICING["featured"])
        self.assertEqual(payment.status, Payment.Status.PENDING)
        room.refresh_from_db()
        self.assertEqual(room.tier, Room.Tier.FREE)

        # 2. Gateway success callback — the ONLY place a tier can be granted.
        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "VALID", "amount": str(payment.amount), "val_id": "V-123"},
        ) as mock_validate:
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "V-123"},
                format="json",
            )
        mock_validate.assert_called_once_with("V-123")
        self.assertEqual(res.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=success", res.url)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertTrue(
            PaymentAuditLog.objects.filter(payment=payment, new_status="success").exists()
        )

        room.refresh_from_db()
        self.assertEqual(room.tier, Room.Tier.FEATURED)
        self.assertTrue(room.is_featured)
        self.assertGreater(
            room.tier_expires_at,
            timezone.now() + timedelta(days=settings.LISTING_TIER_DURATION_DAYS - 1),
        )

        # The landlord is notified the promotion activated.
        notif = self.landlord.notifications.filter(
            notification_type=Notification.Type.PAYMENT_SUCCESS
        ).latest("created_at")
        self.assertIn("Listing promoted", notif.title)
        self.assertIn(room.title, notif.message)

        # 3. Expiry: 30 days have passed — revert to Free and email the owner.
        Room.objects.filter(pk=room.pk).update(tier_expires_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(len(mail.outbox), 0)
        result = expire_listing_tiers()
        self.assertEqual(result["expired"], 1)

        room.refresh_from_db()
        self.assertEqual(room.tier, Room.Tier.FREE)
        self.assertIsNone(room.tier_expires_at)
        self.assertFalse(room.is_featured)

        self.assertEqual(len(mail.outbox), 1)
        expiry_email = mail.outbox[0]
        self.assertEqual(expiry_email.to, [self.landlord.email])
        self.assertIn("promotion has ended", expiry_email.subject.lower())
        self.assertTrue(expiry_email.alternatives, "expiry email must carry an HTML body")

        # The room API now reports it as free again.
        res = self.client.get(f"/api/v1/rooms/{room.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("tier", res.data)
        self.assertEqual(res.data["tier"], Room.Tier.FREE)

    @patch("payments.services.bkash.create_payment")
    def test_premium_upgrade_via_bkash_callback(self, mock_create):
        """Premium through the bKash two-step callback (query + execute)."""
        mock_create.return_value = {"bkashURL": "https://gw.example/bkash"}
        room = self._publish_room()

        res = self._initiate(room, "premium", method="bkash")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["bkash_url"], "https://gw.example/bkash")
        payment = Payment.objects.get(transaction_id=res.data["transaction_id"])
        self.assertEqual(payment.payment_type, Payment.Type.LISTING_PREMIUM)
        self.assertEqual(payment.amount, settings.LISTING_TIER_PRICING["premium"])

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
        self.assertEqual(res.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=success", res.url)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.gateway_transaction_id, "TRX-1")

        room.refresh_from_db()
        self.assertEqual(room.tier, Room.Tier.PREMIUM)
        self.assertTrue(room.is_featured)

    @patch("payments.services.sslcommerz.initiate_payment")
    def test_failed_validation_never_grants_tier(self, mock_initiate):
        """A forged callback (VALID not confirmed) fails the payment — no tier."""
        mock_initiate.return_value = {"GatewayPageURL": "https://gw.example/pay"}
        room = self._publish_room()
        res = self._initiate(room, "featured")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        payment = Payment.objects.get(transaction_id=res.data["transaction_id"])

        with patch(
            "payments.services.sslcommerz.validate_payment",
            return_value={"status": "INVALID"},
        ):
            res = self.client.post(
                "/api/v1/payments/sslcommerz/success/",
                {"tran_id": payment.transaction_id, "val_id": "FAKE"},
                format="json",
            )
        self.assertEqual(res.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=fail", res.url)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        room.refresh_from_db()
        self.assertEqual(room.tier, Room.Tier.FREE)
        self.assertFalse(room.is_featured)
