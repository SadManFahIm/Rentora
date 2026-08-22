"""Tests for insurance & credit partners — deterministic rule-based quoting,
idempotent policy issuance, and credit eligibility scoring.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from brokers.models import BrokerProfile
from monetization.models import Commission, RevenueLedgerEntry
from notifications.models import Notification
from rooms.models import Room

from .models import InsuranceProduct, InsuranceQuote, Partner
from .providers import RuleBasedInsuranceProvider, get_insurance_provider
from .services import PartnerServiceError, check_credit_eligibility, create_quote, issue_policy

User = get_user_model()


def make_room(owner, price=15000, **kw):
    defaults = dict(
        title="Ins Room",
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


class RuleProviderTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="ins_owner", email="io@example.com", password="test12345"
        )
        self.partner = Partner.objects.create(
            name="Bikroy Insurance", kind="insurance", code="bikroy-ins"
        )
        self.product = InsuranceProduct.objects.create(
            partner=self.partner, code="rent-shield", name="Rent Shield", price_monthly=500
        )
        self.room = make_room(self.owner, price=15000)

    def test_provider_selection_defaults_to_rule(self):
        self.assertIsInstance(get_insurance_provider(), RuleBasedInsuranceProvider)

    def test_quote_math_room_factor_and_verified_discount(self):
        user = User.objects.create_user(
            username="ins_tenant",
            email="it@example.com",
            password="test12345",
            tenant_verified=True,
        )
        result = RuleBasedInsuranceProvider().quote(self.product, user, self.room)
        # room price / 15000 = 1.0 -> factor 1.0; verified tenant -5%.
        self.assertEqual(result["price"], Decimal("475.00"))
        self.assertIn("verified tenant -5%", result["reasons"])

    def test_quote_math_caps_room_factor(self):
        user = User.objects.create_user(
            username="ins_tenant2", email="it2@example.com", password="test12345", nid_verified=True
        )
        rich_room = make_room(self.owner, price=90000)  # factor clamps to 1.0
        result = RuleBasedInsuranceProvider().quote(self.product, user, rich_room)
        self.assertEqual(result["price"], Decimal("485.00"))  # -3% NID


class IssuePolicyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="iss_owner", email="is@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="iss_tenant", email="it@example.com", password="test12345"
        )
        self.broker_user = User.objects.create_user(
            username="iss_broker", email="ib@example.com", password="test12345"
        )
        self.broker = BrokerProfile.objects.create(
            user=self.broker_user, status=BrokerProfile.Status.VERIFIED
        )
        self.partner = Partner.objects.create(
            name="Partner Co", kind="insurance", code="partner-co"
        )
        self.product = InsuranceProduct.objects.create(
            partner=self.partner, code="shield", name="Shield", price_monthly=1000
        )
        self.room = make_room(self.owner, price=15000)

    def _quote(self):
        return create_quote(
            user=self.tenant, product=self.product, room=self.room, broker=self.broker
        )

    def test_issue_settles_commission_ledger_and_notifies(self):
        quote = self._quote()
        issue_policy(quote, self.tenant)
        quote.refresh_from_db()
        self.assertEqual(quote.status, InsuranceQuote.Status.ISSUED)

        # Broker earns 2% of the premium.
        broker_commission = Commission.objects.get(idempotency_key=f"insurance-broker-{quote.pk}")
        self.assertEqual(broker_commission.amount, Decimal("20.00"))
        self.assertEqual(broker_commission.recipient, self.broker_user)

        # Platform revenue = 8% of premium; partner keeps the rest.
        entry = RevenueLedgerEntry.objects.get(idempotency_key=f"insurance-policy-{quote.pk}")
        self.assertEqual(entry.platform_amount, Decimal("80.00"))
        self.assertEqual(entry.partner_amount, Decimal("920.00"))

        self.assertTrue(
            Notification.objects.filter(
                user=self.tenant,
                notification_type=Notification.Type.INSURANCE_POLICY_ISSUED,
            ).exists()
        )

    def test_issue_is_single_transition(self):
        quote = self._quote()
        issue_policy(quote, self.tenant)
        with self.assertRaises(PartnerServiceError):
            issue_policy(quote, self.tenant)
        self.assertEqual(Commission.objects.count(), 1)

    def test_quote_price_is_persisted_from_provider(self):
        quote = self._quote()
        self.assertGreater(quote.price, 0)
        self.assertIn("provider", quote.quote_data)


class CreditEligibilityTests(TestCase):
    def setUp(self):
        self.verified = User.objects.create_user(
            username="credit_ok", email="ck@example.com", password="test12345", tenant_verified=True
        )
        self.fresh = User.objects.create_user(
            username="credit_new", email="cn@example.com", password="test12345"
        )

    def test_verified_tenant_is_eligible(self):
        out = check_credit_eligibility(self.verified)
        self.assertTrue(out["eligible"])
        self.assertGreaterEqual(out["credit_score"], 420)
        self.assertGreater(out["preapproved_limit"], 0)
        self.assertEqual(out["provider"], "rule")

    def test_fresh_tenant_is_not_eligible(self):
        out = check_credit_eligibility(self.fresh)
        self.assertFalse(out["eligible"])
        self.assertEqual(out["preapproved_limit"], 0)
