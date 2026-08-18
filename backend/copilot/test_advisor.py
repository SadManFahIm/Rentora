"""Tests for the Tier-4 advisory engines — rental advisor, negotiation
assistant, agreement checker, landlord copilot.

Properties under test:

- Advisor: recommendations are grounded in real market data, never invented.
- Negotiation: the suggested offer is derived from the area market.
- Agreement checker: clause detection + honest missing-clause list.
- Landlord copilot: owner-scoped (404 for someone else's listing) and
  grounded in the room's own booking/wishlist data.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from copilot.advisor import agreement_check, landlord_insights, negotiation_draft, rental_advice
from pricing.models import MarketStat
from rooms.models import Room

User = get_user_model()


def make_room(owner, area="Dhanmondi", price=14000, **kw):
    defaults = dict(
        title="Bright Studio, Dhanmondi",
        description="A bright furnished studio near Rapa Plaza with attached bath.",
        room_type="studio",
        price=price,
        area=area,
        address="Road 6, Dhanmondi",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi", "furnished", "attached bath"],
        size_sqft=320,
        verified=True,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, **defaults)


class RentalAdvisorTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="adv_owner", password="test12345")

    def test_recommendation_grounded_in_market_stat(self):
        MarketStat.objects.create(
            area="Dhanmondi",
            room_type="studio",
            avg_price=15000,
            median_price=14500,
            min_price=10000,
            max_price=20000,
            percentile_25=12000,
            percentile_75=17000,
            sample_size=12,
        )
        out = rental_advice(budget_max=15000, room_type="studio")
        rec = next((r for r in out["recommendations"] if r["area"] == "Dhanmondi"), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["median_rent"], 14500)
        self.assertTrue(rec["fits_budget"])
        self.assertIn("checklist", out)

    def test_affordability_rule(self):
        out = rental_advice(budget_max=30000, monthly_income=100000)
        self.assertEqual(out["affordability"]["ratio"], 0.3)
        self.assertEqual(out["affordability"]["level"], "comfortable")

    def test_high_income_ratio_flag(self):
        out = rental_advice(budget_max=60000, monthly_income=100000)
        self.assertEqual(out["affordability"]["level"], "high")


class NegotiationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="neg_owner", password="test12345")

    def test_offer_uses_market_percentile(self):
        room = make_room(self.owner, price=20000)
        MarketStat.objects.create(
            area="Dhanmondi",
            room_type="studio",
            avg_price=15000,
            median_price=14500,
            min_price=10000,
            max_price=20000,
            percentile_25=12000,
            percentile_75=17000,
            sample_size=12,
        )
        out = negotiation_draft(room, role="tenant")
        self.assertGreaterEqual(out["suggested_offer"], 12000)
        self.assertIn("৳", out["draft_bn"])
        self.assertIn("৳", out["draft_en"])

    def test_explicit_target_price_wins(self):
        room = make_room(self.owner, price=20000)
        out = negotiation_draft(room, target_price=13000)
        self.assertEqual(out["suggested_offer"], 13000)


class AgreementCheckerTests(TestCase):
    def test_detects_risky_clauses(self):
        text = (
            "The landlord may increase rent by 20% every six months. "
            "Tenant must give 60 days notice. Security deposit of two months "
            "is refundable on move-out. Maintenance of appliances is the "
            "tenant's responsibility."
        )
        out = agreement_check(text)
        self.assertEqual(out["verdict"], "review")
        clauses = {c["clause"] for c in out["clauses"]}
        self.assertIn("rent_increase", clauses)
        self.assertIn("notice_period", clauses)
        self.assertIn("deposit", clauses)
        self.assertIn("maintenance", clauses)

    def test_missing_clauses_are_listed(self):
        out = agreement_check("Just a short agreement without many clauses.")
        self.assertIn("deposit", out["missing"])
        self.assertIn("disclaimer", out)

    def test_empty_text(self):
        out = agreement_check("")
        self.assertEqual(out["verdict"], "empty")


class LandlordCopilotTests(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ll_owner", email="ll_owner@example.com", password="test12345", is_staff=False
        )
        self.other = User.objects.create_user(
            username="ll_other", email="ll_other@example.com", password="test12345"
        )
        self.room = make_room(self.landlord, price=20000)

    def test_insights_grounded(self):
        out = landlord_insights(self.room)
        self.assertEqual(out["listing_id"], self.room.id)
        self.assertEqual(out["price_compare"]["listing_price"], 20000)
        self.assertIn("interest_30d", out)

    def test_owner_only_endpoint(self):
        self.client.force_authenticate(self.landlord)
        resp = self.client.post(
            "/api/v1/copilot/landlord/", {"listing_id": self.room.id}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["listing_id"], self.room.id)

    def test_other_user_gets_404(self):
        self.client.force_authenticate(self.other)
        resp = self.client.post(
            "/api/v1/copilot/landlord/", {"listing_id": self.room.id}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_auth(self):
        resp = self.client.post(
            "/api/v1/copilot/landlord/", {"listing_id": self.room.id}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AdvisorEndpointsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="ep_owner", password="test12345")

    def test_advisor_endpoint(self):
        resp = self.client.post(
            "/api/v1/copilot/advisor/",
            {"budget_max": 15000, "room_type": "studio"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("recommendations", resp.data)

    def test_negotiation_endpoint(self):
        room = make_room(self.owner)
        resp = self.client.post(
            "/api/v1/copilot/negotiate/",
            {"listing_id": room.id, "role": "tenant"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("draft_en", resp.data)
        self.assertIn("draft_bn", resp.data)

    def test_agreement_endpoint(self):
        resp = self.client.post(
            "/api/v1/copilot/agreement-check/",
            {"text": "Rent may increase by 20% yearly. Deposit refundable."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("verdict", resp.data)
