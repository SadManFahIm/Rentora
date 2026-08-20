"""Phase 15 (C6) — AI Rental Market Report.

Covers the deterministic report engine (live MarketStat prices + demand +
catalogue availability, snapshot history for movement), the baseline honesty
contract, the public read endpoint, the admin generate trigger, and the
weekly subscriber email (opt-in landlords only).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from pricing.models import MarketStat
from rooms.models import Room

from .market_report import build_report, generate_report
from .models import AreaPriceSnapshot

User = get_user_model()


def make_room(owner, area="Uttara", price=12000):
    return Room.objects.create(
        owner=owner,
        title="Bright room",
        description="A furnished room near the station.",
        room_type="single",
        price=price,
        area=area,
        address="Sector 7, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=250,
    )


def make_market_stat(area="Uttara", avg=12000, sample=3):
    return MarketStat.objects.create(
        area=area,
        room_type="single",
        avg_price=avg,
        median_price=avg,
        min_price=avg - 1000,
        max_price=avg + 1000,
        percentile_25=avg - 500,
        percentile_75=avg + 500,
        sample_size=sample,
    )


class MarketReportEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="mr_owner", email="mr_owner@example.com", password="test12345"
        )
        make_room(self.owner, "Uttara")
        make_room(self.owner, "Mirpur")
        make_market_stat("Uttara", avg=12000)
        make_market_stat("Mirpur", avg=8000)

    def test_build_report_is_read_only_and_baseline(self):
        report = build_report()
        self.assertEqual(report["baseline"], True)
        self.assertEqual(len(report["areas"]), 2)
        self.assertEqual(AreaPriceSnapshot.objects.count(), 0)
        self.assertIn("note", report)
        self.assertIn("summary_bn", report)

    def test_baseline_flag_clears_once_history_exists(self):
        week_start = timezone.now().date() - timedelta(days=7)
        AreaPriceSnapshot.objects.create(
            area="Uttara",
            room_type="single",
            week_start=week_start,
            avg_price=11000,
            median_price=11000,
            sample_size=2,
        )
        report = build_report()
        self.assertEqual(report["baseline"], False)

    def test_generate_writes_one_snapshot_per_segment(self):
        report = generate_report()
        self.assertEqual(len(report["areas"]), 2)
        self.assertEqual(AreaPriceSnapshot.objects.count(), 2)

        report2 = generate_report()  # same week — upsert, not duplicates
        self.assertEqual(AreaPriceSnapshot.objects.count(), 2)
        self.assertEqual(report2["week_label"], report["week_label"])

    def test_price_movement_vs_previous_week(self):
        week_start = timezone.now().date() - timedelta(days=7)
        AreaPriceSnapshot.objects.create(
            area="Uttara",
            room_type="single",
            week_start=week_start,
            avg_price=10000,
            median_price=10000,
            sample_size=2,
        )
        report = build_report()
        uttara = next(a for a in report["areas"] if a["area"] == "Uttara")
        self.assertEqual(uttara["prev_avg_price"], 10000)
        self.assertEqual(uttara["price_change_pct"], 20.0)

    def test_areas_without_market_stats_are_honest(self):
        make_room(self.owner, "Gulshan")  # no MarketStat for Gulshan
        report = build_report()
        gulshan = next(a for a in report["areas"] if a["area"] == "Gulshan")
        self.assertIsNone(gulshan["avg_price"])
        self.assertIsNone(gulshan["median_price"])
        self.assertIsNone(gulshan["price_change_pct"])
        self.assertEqual(gulshan["total_count"], 1)

    def test_availability_from_catalogue(self):
        report = build_report()
        uttara = next(a for a in report["areas"] if a["area"] == "Uttara")
        self.assertEqual(uttara["available_count"], 1)
        self.assertEqual(uttara["total_count"], 1)
        self.assertEqual(uttara["availability_pct"], 100)


class MarketReportEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="mr_ep_owner", email="mr_ep_owner@example.com", password="test12345"
        )
        make_room(self.owner, "Uttara")
        make_market_stat("Uttara")

    def test_public_get_returns_report(self):
        resp = self.client.get("/api/v1/analytics/market-report/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("week_label", resp.data)
        self.assertIn("areas", resp.data)
        self.assertIn("summary_bn", resp.data)
        self.assertEqual(AreaPriceSnapshot.objects.count(), 0)  # read path never mutates

    def test_generate_requires_authentication(self):
        resp = self.client.post("/api/v1/analytics/market-report/generate/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_rejects_non_admin(self):
        self.client.force_authenticate(self.owner)
        resp = self.client.post("/api/v1/analytics/market-report/generate/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_generate_as_admin_writes_snapshot(self):
        admin = User.objects.create_user(
            username="mr_admin",
            email="mr_admin@example.com",
            password="test12345",
            is_staff=True,
        )
        self.client.force_authenticate(admin)
        resp = self.client.post("/api/v1/analytics/market-report/generate/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["ok"], True)
        self.assertEqual(AreaPriceSnapshot.objects.count(), 1)


class MarketReportEmailTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="mr_mail_landlord",
            email="mr_mail_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            market_report_emails_enabled=True,
        )
        self.tenant = User.objects.create_user(
            username="mr_mail_tenant",
            email="mr_mail_tenant@example.com",
            password="test12345",
            market_report_emails_enabled=True,
        )
        make_room(self.landlord, "Uttara")
        make_market_stat("Uttara")

    def test_opted_in_landlord_gets_email(self):
        report = generate_report()
        self.assertEqual(report["emails_sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Rental Market Report", mail.outbox[0].subject)
        self.assertIn("Uttara", mail.outbox[0].body)

    def test_unsubscribed_landlord_gets_no_email(self):
        self.landlord.market_report_emails_enabled = False
        self.landlord.save(update_fields=["market_report_emails_enabled"])
        report = generate_report()
        self.assertEqual(report["emails_sent"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_tenants_never_receive_market_email(self):
        # The tenant is opted in but the report is a landlord newsletter.
        self.landlord.market_report_emails_enabled = False
        self.landlord.save(update_fields=["market_report_emails_enabled"])
        report = generate_report()
        self.assertEqual(report["emails_sent"], 0)
        self.assertEqual(len(mail.outbox), 0)
