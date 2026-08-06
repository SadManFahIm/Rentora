"""Unit tests for the fraud-detection engine.

Each detector is a pure-ish function over a ``Room``; ``run_scan`` persists a
``FraudReport`` + ``FraudSignal`` rows. Tests cover every detector plus the
aggregation math, idempotent re-scan, the auto-scan signal, and permission
gating in the views. Uses Django's built-in ``TestCase`` like the rest of the
project.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from fraud.models import FraudReport, FraudSignal
from fraud.services.detectors import (
    _duplicate_listing,
    _missing_images,
    _rapid_listing,
    _unverified_owner,
    _suspicious_price,
    run_scan,
)
from pricing.models import MarketStat
from rooms.models import Room

User = get_user_model()


def make_user(username, nid_verified=False):
    return User.objects.create_user(
        username=username, password="test12345", nid_verified=nid_verified
    )


def make_room(
    owner,
    title="Cozy Single, Mirpur",
    description="Nice room near the station.",
    area="Mirpur",
    room_type="single",
    price=8000,
    is_available=True,
):
    return Room.objects.create(
        owner=owner,
        title=title,
        description=description,
        room_type=room_type,
        price=price,
        area=area,
        address="12 Mirpur Road",
        lat=23.8069,
        lng=90.3687,
        amenities=["wifi"],
        size_sqft=250,
        is_available=is_available,
    )


class DuplicateListingTests(TestCase):
    def test_identical_title_in_same_area_flags(self):
        owner = make_user("owner1")
        make_room(owner, title="Modern Studio, Mirpur")
        dup = make_room(owner, title="Modern Studio, Mirpur")
        signal = _duplicate_listing(dup)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.detector, FraudSignal.Detector.DUPLICATE_LISTING)
        self.assertEqual(signal.severity, FraudReport.Severity.HIGH)

    def test_distinct_title_in_same_area_clean(self):
        owner = make_user("owner1")
        make_room(owner, title="Modern Studio, Mirpur")
        other = make_room(owner, title="Garden View Flat, Mirpur")
        self.assertIsNone(_duplicate_listing(other))

    def test_same_title_different_area_clean(self):
        owner = make_user("owner1")
        make_room(owner, title="Modern Studio, Mirpur", area="Mirpur")
        other = make_room(owner, title="Modern Studio, Mirpur", area="Dhanmondi")
        self.assertIsNone(_duplicate_listing(other))


class DescriptionSimilarityTests(TestCase):
    def test_copied_description_flags(self):
        owner = make_user("owner1")
        text = "Bright modern studio close to the metro station, ideal for students."
        make_room(owner, description=text)
        dup = make_room(owner, description=text)
        signal = _duplicate_listing  # reused: description detector is tested below
        # The description detector lives in detectors.py; call it directly.
        from fraud.services.detectors import _description_similarity

        self.assertIsNotNone(_description_similarity(dup))

    def test_distinct_description_clean(self):
        owner = make_user("owner1")
        make_room(owner, description="Bright modern studio close to the metro station.")
        other = make_room(owner, description="A quiet garden house away from traffic.")
        from fraud.services.detectors import _description_similarity

        self.assertIsNone(_description_similarity(other))


class SuspiciousPriceTests(TestCase):
    def _stat(self, area="Mirpur", room_type="single", p25=7000, p75=10000):
        MarketStat.objects.create(
            area=area,
            room_type=room_type,
            avg_price=8500,
            median_price=8500,
            min_price=5000,
            max_price=12000,
            percentile_25=p25,
            percentile_75=p75,
            sample_size=20,
        )

    def test_too_cheap_flags_medium(self):
        self._stat(p25=7000)
        room = make_room(make_user("o"), price=3000)
        signal = _suspicious_price(room)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.severity, FraudReport.Severity.MEDIUM)
        self.assertEqual(signal.detector, FraudSignal.Detector.SUSPICIOUS_PRICE)

    def test_too_expensive_flags_low(self):
        self._stat(p75=10000)
        room = make_room(make_user("o"), price=18000)
        signal = _suspicious_price(room)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.severity, FraudReport.Severity.LOW)

    def test_fair_price_clean(self):
        self._stat(p25=7000, p75=10000)
        room = make_room(make_user("o"), price=8500)
        self.assertIsNone(_suspicious_price(room))

    def test_no_market_stat_clean(self):
        room = make_room(make_user("o"), price=1)
        self.assertIsNone(_suspicious_price(room))

    def test_small_sample_clean(self):
        MarketStat.objects.create(
            area="Mirpur",
            room_type="single",
            avg_price=8500,
            median_price=8500,
            min_price=5000,
            max_price=12000,
            percentile_25=7000,
            percentile_75=10000,
            sample_size=2,
        )
        room = make_room(make_user("o"), price=3000)
        self.assertIsNone(_suspicious_price(room))


class MissingImagesTests(TestCase):
    def test_no_images_flags_low(self):
        room = make_room(make_user("o"))
        signal = _missing_images(room)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.severity, FraudReport.Severity.LOW)

    def test_with_image_clean(self):
        room = make_room(make_user("o"))
        room.images.create(image="http://example.com/room.jpg", is_primary=True)
        self.assertIsNone(_missing_images(room))


class UnverifiedOwnerTests(TestCase):
    def test_unverified_owner_flags_low(self):
        room = make_room(make_user("o", nid_verified=False))
        signal = _unverified_owner(room)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.severity, FraudReport.Severity.LOW)

    def test_verified_owner_clean(self):
        room = make_room(make_user("o", nid_verified=True))
        self.assertIsNone(_unverified_owner(room))


class RapidListingTests(TestCase):
    def test_many_rooms_in_window_flags_medium(self):
        owner = make_user("o")
        make_room(owner, title="Room A")
        make_room(owner, title="Room B")
        make_room(owner, title="Room C")
        fourth = make_room(owner, title="Room D")
        signal = _rapid_listing(fourth)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.severity, FraudReport.Severity.MEDIUM)

    def test_few_rooms_clean(self):
        owner = make_user("o")
        make_room(owner, title="Room A")
        second = make_room(owner, title="Room B")
        self.assertIsNone(_rapid_listing(second))


class RunScanTests(TestCase):
    def test_clean_room_produces_clean_report(self):
        owner = make_user("o", nid_verified=True)
        room = make_room(owner)
        room.images.create(image="http://example.com/room.jpg")
        MarketStat.objects.create(
            area="Mirpur",
            room_type="single",
            avg_price=8500,
            median_price=8500,
            min_price=5000,
            max_price=12000,
            percentile_25=7000,
            percentile_75=10000,
            sample_size=20,
        )
        report = run_scan(room)
        self.assertEqual(report.severity, FraudReport.Severity.CLEAN)
        self.assertEqual(report.score, 0)
        self.assertFalse(report.is_flagged)

    def test_duplicate_room_gets_high_severity_and_signals(self):
        owner = make_user("o")
        original = make_room(owner, title="Modern Studio, Mirpur")
        original.images.create(image="http://example.com/room.jpg")
        dup = make_room(owner, title="Modern Studio, Mirpur", price=1)
        report = run_scan(dup)
        self.assertEqual(report.severity, FraudReport.Severity.HIGH)
        self.assertEqual(report.score, 100)
        self.assertTrue(report.is_flagged)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.DUPLICATE_LISTING, detectors)
        self.assertIn(FraudSignal.Detector.MISSING_IMAGES, detectors)

    def test_rescan_is_idempotent_and_replaces_signals(self):
        owner = make_user("o", nid_verified=True)
        room = make_room(owner, title="Modern Studio, Mirpur")
        # First scan: flagged (missing images).
        report1 = run_scan(room)
        self.assertGreater(report1.score, 0)
        first_signal_count = report1.signals.count()
        # Fix the room, rescan: should be clean and signals replaced.
        room.images.create(image="http://example.com/room.jpg")
        report2 = run_scan(room)
        self.assertEqual(report2.score, 0)
        self.assertEqual(report2.signals.count(), 0)
        # Same report row (OneToOne), signals replaced not duplicated.
        self.assertEqual(FraudReport.objects.filter(room=room).count(), 1)
        self.assertLess(report2.signals.count(), first_signal_count)


class FraudSignalAutoScanTests(TestCase):
    def test_creating_room_auto_scans_and_notifies(self):
        owner = make_user("o")
        # An existing listing makes the new one an obvious duplicate → HIGH,
        # which is the severity that warrants a landlord notification.
        make_room(owner, title="Modern Studio, Mirpur")
        room = make_room(owner, title="Modern Studio, Mirpur")
        report = FraudReport.objects.filter(room=room).first()
        self.assertIsNotNone(report)
        self.assertEqual(report.severity, FraudReport.Severity.HIGH)
        # Landlord notification was created by the signal.
        self.assertTrue(
            owner.notifications.filter(notification_type="fraud_flag").exists()
        )

    def test_low_severity_room_does_not_notify(self):
        # A brand-new listing with nothing to compare against only trips
        # low-severity signals (missing images / unverified owner), which are
        # informational and must not interrupt the landlord.
        owner = make_user("o")
        make_room(owner, title="Lonely Studio, Mirpur")
        self.assertFalse(
            owner.notifications.filter(notification_type="fraud_flag").exists()
        )


class FraudViewPermissionTests(APITestCase):
    def setUp(self):
        self.owner = make_user("owner")
        self.other = make_user("other")
        self.room = make_room(self.owner, title="Modern Studio, Mirpur")
        run_scan(self.room)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_status_endpoint_is_public(self):
        res = self.client.get(f"/api/v1/fraud/rooms/{self.room.pk}/status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("severity", res.data)
        self.assertIn("score", res.data)

    def test_owner_can_list_own_reports_only(self):
        self._auth(self.owner)
        res = self.client.get("/api/v1/fraud/reports/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # `room` is a nested summary object (RoomListSerializer), not a bare pk.
        self.assertEqual({r["room"]["id"] for r in res.data}, {self.room.pk})

    def test_other_user_cannot_see_foreign_reports(self):
        self._auth(self.other)
        res = self.client.get("/api/v1/fraud/reports/")
        self.assertEqual(res.data, [])

    def test_owner_can_rescan_own_room(self):
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/fraud/rooms/{self.room.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_other_user_cannot_rescan(self):
        self._auth(self.other)
        res = self.client.post(f"/api/v1/fraud/rooms/{self.room.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_list_reports(self):
        res = self.client.get("/api/v1/fraud/reports/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_cannot_review(self):
        self._auth(self.owner)
        report = FraudReport.objects.get(room=self.room)
        res = self.client.post(
            f"/api/v1/fraud/reports/{report.pk}/review/",
            {"action": "reviewed"},
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_review(self):
        admin = User.objects.create_user(
            username="boss", password="x", is_staff=True
        )
        self._auth(admin)
        report = FraudReport.objects.get(room=self.room)
        res = self.client.post(
            f"/api/v1/fraud/reports/{report.pk}/review/",
            {"action": "reviewed"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.status, FraudReport.Status.REVIEWED)


class DetectorRegistrationTests(TestCase):
    def test_all_detectors_registered(self):
        from fraud.services.detectors import DETECTORS

        keys = {d.__name__ for d in DETECTORS}
        self.assertEqual(
            keys,
            {
                "_duplicate_listing",
                "_description_similarity",
                "_suspicious_price",
                "_missing_images",
                "_unverified_owner",
                "_rapid_listing",
            },
        )
