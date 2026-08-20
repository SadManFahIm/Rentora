"""Tests for the add-on marketplace — deterministic recommendations and
idempotent order confirmation (provider + broker commissions, ledger).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from monetization.models import Commission, RevenueLedgerEntry
from notifications.models import Notification
from rooms.models import Room

from .models import AddonOrder, AddonProvider, AddonService
from .services import MarketplaceError, confirm_order, recommend_addons

User = get_user_model()


def make_room(owner, price=10000, **kw):
    defaults = dict(
        title="Mkt Room",
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


class RecommendTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="mkt_owner", email="mo@example.com", password="test12345"
        )
        self.room = make_room(self.owner)
        self.provider = AddonProvider.objects.create(
            user=self.owner, business_name="CleanCo", status=AddonProvider.Status.ACTIVE
        )
        self.suspended = AddonProvider.objects.create(
            user=User.objects.create_user(
                username="mkt_susp", email="susp@example.com", password="test12345"
            ),
            business_name="BadCo",
            status=AddonProvider.Status.SUSPENDED,
        )
        self.furniture = AddonService.objects.create(
            provider=self.provider,
            category=AddonService.Category.FURNITURE,
            title="Bed",
            price=5000,
        )
        self.insurance = AddonService.objects.create(
            provider=self.provider,
            category=AddonService.Category.INSURANCE,
            title="Policy",
            price=300,
        )
        self.inactive = AddonService.objects.create(
            provider=self.provider,
            category=AddonService.Category.CLEANING,
            title="Deep clean",
            price=800,
            is_active=False,
        )
        self.suspended_service = AddonService.objects.create(
            provider=self.suspended,
            category=AddonService.Category.REPAIRS,
            title="Plumbing",
            price=400,
        )

    def test_recommendation_prioritizes_insurance_then_excludes_inactive(self):
        result = recommend_addons(self.room, limit=4)
        titles = [s.title for s in result]
        self.assertIn("Policy", titles)
        self.assertNotIn("Deep clean", titles)
        self.assertNotIn("Plumbing", titles)
        self.assertEqual(titles[0], "Policy")

    def test_recommendation_sorted_by_category_priority(self):
        result = recommend_addons(self.room, limit=4)
        order = {AddonService.Category.INSURANCE: 0, AddonService.Category.FURNITURE: 4}
        categories = [s.category for s in result]
        self.assertLess(
            order[categories[0]],
            order[categories[1]],
        )


class ConfirmOrderTests(TestCase):
    def setUp(self):
        self.tenant = User.objects.create_user(
            username="mkt_tenant", email="mt@example.com", password="test12345"
        )
        self.provider_user = User.objects.create_user(
            username="mkt_provider", email="mp@example.com", password="test12345"
        )
        self.broker_user = User.objects.create_user(
            username="mkt_broker", email="mb@example.com", password="test12345"
        )
        from brokers.models import BrokerProfile

        self.broker = BrokerProfile.objects.create(
            user=self.broker_user, status=BrokerProfile.Status.VERIFIED
        )
        self.provider = AddonProvider.objects.create(
            user=self.provider_user,
            business_name="ReloPro",
            status=AddonProvider.Status.ACTIVE,
            commission_rate=Decimal("15.00"),
        )
        self.service = AddonService.objects.create(
            provider=self.provider,
            category=AddonService.Category.RELOCATION,
            title="Move-in",
            price=10000,
        )
        self.order = AddonOrder.objects.create(
            service=self.service, tenant=self.tenant, quantity=1, broker=self.broker
        )

    def test_confirm_settles_commissions_and_ledger(self):
        confirm_order(self.order, self.tenant)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, AddonOrder.Status.CONFIRMED)

        # Provider gets its own 15% rate; broker gets the 2% referral rate.
        provider_commission = Commission.objects.get(
            idempotency_key=f"marketplace-provider-{self.order.pk}"
        )
        broker_commission = Commission.objects.get(
            idempotency_key=f"marketplace-broker-{self.order.pk}"
        )
        self.assertEqual(provider_commission.amount, Decimal("1500.00"))
        self.assertEqual(broker_commission.amount, Decimal("200.00"))

        # Platform keeps the remainder, written exactly once.
        entry = RevenueLedgerEntry.objects.get(idempotency_key=f"marketplace-sale-{self.order.pk}")
        self.assertEqual(entry.platform_amount, Decimal("8300.00"))
        self.assertEqual(entry.partner_amount, Decimal("1700.00"))

        self.assertTrue(
            Notification.objects.filter(
                user=self.provider_user,
                notification_type=Notification.Type.ADDON_ORDER_CONFIRMED,
            ).exists()
        )

    def test_confirm_is_single_transition(self):
        confirm_order(self.order, self.tenant)
        with self.assertRaises(MarketplaceError):
            confirm_order(self.order, self.tenant)
        self.assertEqual(Commission.objects.count(), 2)

    def test_no_broker_means_full_share_to_partner(self):
        self.order.broker = None
        self.order.save()
        confirm_order(self.order, self.tenant)
        entry = RevenueLedgerEntry.objects.get(idempotency_key=f"marketplace-sale-{self.order.pk}")
        self.assertEqual(entry.platform_amount, Decimal("8500.00"))
        self.assertEqual(entry.partner_amount, Decimal("1500.00"))
