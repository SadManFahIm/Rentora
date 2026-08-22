"""Phase 17 -- Stage 5: Photo-Geo Authenticity Tests."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from config.trust_utils import compute_haversine_distance
from fraud.models import FraudReport, FraudSignal
from fraud.services.photo_geo import (
    check_photo_geo_mismatch,
    create_photo_geo_signal,
    extract_gps_for_room_image,
    get_threshold_km,
    scan_room_photo_geo,
)
from rooms.models import Room, RoomImage
from users.models import User


def _create_user(**kwargs):
    defaults = {"username": "owner", "email": "owner@example.com"}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults, password="testpass123")


def _create_room(owner, **kwargs):
    defaults = {
        "title": "Test Room",
        "description": "A test room",
        "room_type": "single",
        "price": Decimal("5000.00"),
        "area": "Dhanmondi",
        "address": "123 Road, Dhanmondi",
        "lat": Decimal("23.7509"),
        "lng": Decimal("90.3766"),
        "amenities": [],
        "size_sqft": 200,
    }
    defaults.update(kwargs)
    return Room.objects.create(owner=owner, **defaults)


# -- Haversine Tests --


class HaversineTest(TestCase):
    def test_same_point_zero(self):
        dist = compute_haversine_distance(23.7509, 90.3766, 23.7509, 90.3766)
        self.assertAlmostEqual(dist, 0, places=1)

    def test_known_distance(self):
        # Dhanmondi to Gulshan ~5km
        dist = compute_haversine_distance(23.7509, 90.3766, 23.7925, 90.4078)
        self.assertGreater(dist, 3000)
        self.assertLess(dist, 7000)

    def test_far_distance(self):
        # Dhaka to Chittagong ~250km
        dist = compute_haversine_distance(23.8103, 90.4125, 22.3569, 91.7832)
        self.assertGreater(dist, 200000)


# -- Threshold Tests --


class ThresholdTest(TestCase):
    def test_default_threshold(self):
        self.assertEqual(get_threshold_km(), 5.0)

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=10.0)
    def test_custom_threshold(self):
        self.assertEqual(get_threshold_km(), 10.0)


# -- extract_gps_for_room_image Tests --


class ExtractGpsTest(TestCase):
    def setUp(self):
        self.user = _create_user()
        self.room = _create_room(self.user)

    @patch("config.exif_utils.extract_gps_from_exif")
    def test_extract_success(self, mock_extract):
        mock_extract.return_value = (23.8000, 90.4100, "high")
        img = RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
        )
        mock_open = MagicMock()
        mock_open.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=b"\xff\xd8"))
        )
        mock_open.__exit__ = MagicMock(return_value=False)
        with patch("builtins.open", mock_open), patch("os.path.exists", return_value=True):
            result = extract_gps_for_room_image(img)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 23.8000)

    @patch("config.exif_utils.extract_gps_from_exif")
    def test_extract_no_gps(self, mock_extract):
        mock_extract.return_value = None
        img = RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
        )
        mock_open = MagicMock()
        mock_open.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=b"\xff\xd8"))
        )
        mock_open.__exit__ = MagicMock(return_value=False)
        with patch("builtins.open", mock_open), patch("os.path.exists", return_value=True):
            result = extract_gps_for_room_image(img)
        self.assertIsNone(result)

    def test_extract_no_file(self):
        img = RoomImage.objects.create(room=self.room)
        result = extract_gps_for_room_image(img)
        self.assertIsNone(result)
        self.assertIsNone(img.photo_lat)


# -- check_photo_geo_mismatch Tests --


class CheckMismatchTest(TestCase):
    def setUp(self):
        self.user = _create_user()
        self.room = _create_room(self.user)

    def test_no_gps_photos(self):
        result = check_photo_geo_mismatch(self.room)
        self.assertFalse(result["mismatch"])

    def test_no_room_lat_lng(self):
        room2 = _create_room(self.user, lat=Decimal("0"), lng=Decimal("0"))
        RoomImage.objects.create(
            room=room2,
            image="rooms/test.jpg",
            photo_lat=Decimal("23.8000"),
            photo_lng=Decimal("90.4100"),
        )
        # Room with lat=0, lng=0 is far from the photo — but that's still
        # a valid lat/lng so the mismatch should be detected.
        result = check_photo_geo_mismatch(room2)
        self.assertTrue(result["mismatch"])

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=5.0)
    def test_nearby_photo_no_mismatch(self):
        # Photo GPS very close to room GPS
        RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
            photo_lat=Decimal("23.7510"),
            photo_lng=Decimal("90.3767"),
        )
        result = check_photo_geo_mismatch(self.room)
        self.assertFalse(result["mismatch"])

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=2.0)
    def test_far_photo_mismatch(self):
        # Photo GPS ~30km away (Chittagong-ish)
        RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
            photo_lat=Decimal("22.3569"),
            photo_lng=Decimal("91.7832"),
        )
        result = check_photo_geo_mismatch(self.room)
        self.assertTrue(result["mismatch"])
        self.assertGreater(result["max_distance_km"], 100)

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=1.0)
    def test_mixed_near_and_far(self):
        RoomImage.objects.create(
            room=self.room,
            image="rooms/near.jpg",
            photo_lat=Decimal("23.7510"),
            photo_lng=Decimal("90.3767"),
            is_primary=True,
        )
        RoomImage.objects.create(
            room=self.room,
            image="rooms/far.jpg",
            photo_lat=Decimal("23.9000"),
            photo_lng=Decimal("90.5000"),
        )
        result = check_photo_geo_mismatch(self.room)
        self.assertTrue(result["mismatch"])
        self.assertEqual(len(result["mismatched_images"]), 1)


# -- create_photo_geo_signal Tests --


class CreateSignalTest(TestCase):
    def setUp(self):
        self.user = _create_user()
        self.room = _create_room(self.user)

    def test_no_mismatch_no_signal(self):
        result = {
            "mismatch": False,
            "max_distance_km": 0,
            "mismatched_images": [],
            "threshold_km": 5,
        }
        signal = create_photo_geo_signal(self.room, result)
        self.assertIsNone(signal)

    def test_mismatch_creates_signal(self):
        result = {
            "mismatch": True,
            "max_distance_km": 250.5,
            "mismatched_images": [{"image_id": 1, "distance_km": 250.5}],
            "threshold_km": 5,
        }
        signal = create_photo_geo_signal(self.room, result)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.detector, FraudSignal.Detector.PHOTO_GEO_MISMATCH)
        self.assertEqual(signal.detail["score"], 45)

    def test_no_duplicate_signal(self):
        result = {
            "mismatch": True,
            "max_distance_km": 100,
            "mismatched_images": [{"image_id": 1, "distance_km": 100}],
            "threshold_km": 5,
        }
        create_photo_geo_signal(self.room, result)
        signal2 = create_photo_geo_signal(self.room, result)
        self.assertIsNone(signal2)

    def test_creates_fraud_report(self):
        result = {
            "mismatch": True,
            "max_distance_km": 100,
            "mismatched_images": [{"image_id": 1, "distance_km": 100}],
            "threshold_km": 5,
        }
        create_photo_geo_signal(self.room, result)
        report = FraudReport.objects.get(room=self.room)
        self.assertIn("Photo-geo mismatch", report.summary)


# -- scan_room_photo_geo Tests --


class ScanRoomTest(TestCase):
    def setUp(self):
        self.user = _create_user()
        self.room = _create_room(self.user)

    def test_scan_no_mismatch(self):
        RoomImage.objects.create(
            room=self.room,
            image="rooms/test.jpg",
            photo_lat=Decimal("23.7510"),
            photo_lng=Decimal("90.3767"),
        )
        result = scan_room_photo_geo(self.room)
        self.assertFalse(result["mismatch"])

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=1.0)
    def test_scan_with_mismatch(self):
        RoomImage.objects.create(
            room=self.room,
            image="rooms/far.jpg",
            photo_lat=Decimal("23.9000"),
            photo_lng=Decimal("90.5000"),
        )
        result = scan_room_photo_geo(self.room)
        self.assertTrue(result["mismatch"])
        self.assertTrue(
            FraudSignal.objects.filter(
                report__room=self.room,
                detector=FraudSignal.Detector.PHOTO_GEO_MISMATCH,
            ).exists()
        )


# -- Task Tests --


class ScanPhotoGeoTaskTest(TestCase):
    def test_task_runs(self):
        from fraud.tasks import scan_photo_geo_mismatches

        result = scan_photo_geo_mismatches()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["mismatches"], 0)


# -- API Tests --


class PhotoGeoMismatchesViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(username="admin", email="admin@example.com", is_staff=True)
        self.user = _create_user()
        self.client.force_authenticate(user=self.admin)

    def test_admin_access(self):
        response = self.client.get("/api/v1/fraud/photo-geo/mismatches/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("mismatches", response.data)
        self.assertIn("threshold_km", response.data)

    @override_settings(PHOTO_GEO_MISMATCH_THRESHOLD_KM=1.0)
    def test_returns_mismatches(self):
        room = _create_room(self.user)
        RoomImage.objects.create(
            room=room,
            image="rooms/far.jpg",
            photo_lat=Decimal("23.9000"),
            photo_lng=Decimal("90.5000"),
        )
        response = self.client.get("/api/v1/fraud/photo-geo/mismatches/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 0)

    def test_non_admin_forbidden(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/fraud/photo-geo/mismatches/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
