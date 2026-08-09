"""E2E: the KYC -> verified-badge trust chain, through the real API.

1. An unverified landlord publishes a room -> the listing reports
   ``verified=False`` and ``owner.nid_verified=False``, and the fraud
   auto-scan flags the "unverified owner" signal.
2. An admin approves the landlord's KYC (``nid_verified=True`` — an admin
   action; there is deliberately no self-service endpoint) -> the users
   signal flips ``Room.verified`` on every one of the landlord's listings.
3. The listing API now carries the badge data and a re-scan drops the
   unverified-owner signal.
4. Revoking verification removes the badges again.
5. Roommate matching exposes the KYC state so verified users stand out.

The admin step uses ``user.save()`` on purpose: ``QuerySet.update()`` skips
signals, and this test is exactly about the signal firing.
"""

from django.contrib.auth import get_user_model
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from fraud.models import FraudReport, FraudSignal
from rooms.models import Room

User = get_user_model()


@tag("e2e")
class KYCVerifiedBadgeE2ETest(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="kyc_landlord",
            email="kyc_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=False,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _publish_room(self, title="KYC Test Studio"):
        res = self.client.post(
            "/api/v1/rooms/",
            {
                "title": title,
                "description": "A bright studio awaiting KYC approval.",
                "room_type": "studio",
                "price": "12000.00",
                "area": "Mirpur",
                "address": "12 Mirpur Road",
                "lat": "23.8069",
                "lng": "90.3687",
                "amenities": ["WiFi"],
                "gender_preference": "any",
                "size_sqft": 320,
                "is_available": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return Room.objects.get(pk=res.data["id"])

    def _room_payload(self, room_id):
        res = self.client.get(f"/api/v1/rooms/{room_id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data

    def test_kyc_approval_flips_badge_and_clears_fraud_signal(self):
        self._auth(self.landlord)
        room = self._publish_room()

        # 1. Unverified: no badge, owner unverified, fraud flags it.
        data = self._room_payload(room.pk)
        self.assertFalse(data["verified"])
        self.assertFalse(data["owner"]["nid_verified"])

        report = FraudReport.objects.get(room=room)
        detectors = {s.detector for s in report.signals.all()}
        self.assertIn(FraudSignal.Detector.UNVERIFIED_OWNER, detectors)

        # 2. Admin approves KYC (instance.save() so the signal fires).
        self.landlord.nid_verified = True
        self.landlord.save(update_fields=["nid_verified"])

        # 3. The badge data is now present on the listing…
        data = self._room_payload(room.pk)
        self.assertTrue(data["verified"])
        self.assertTrue(data["owner"]["nid_verified"])

        # …and a re-scan drops the unverified-owner signal.
        self._auth(self.landlord)
        res = self.client.post(f"/api/v1/fraud/rooms/{room.pk}/scan/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        report.refresh_from_db()
        detectors = {s.detector for s in report.signals.all()}
        self.assertNotIn(FraudSignal.Detector.UNVERIFIED_OWNER, detectors)

        # 4. Revoking verification pulls the badges back off.
        self.landlord.nid_verified = False
        self.landlord.save(update_fields=["nid_verified"])
        self._auth(self.landlord)
        data = self._room_payload(room.pk)
        self.assertFalse(data["verified"])
        self.assertFalse(data["owner"]["nid_verified"])

    def test_kyc_sync_covers_all_of_a_landlords_listings(self):
        """KYC approval flips the badge on every listing, not just the newest."""
        self._auth(self.landlord)
        room_a = self._publish_room("KYC Studio A")
        room_b = self._publish_room("KYC Studio B")

        self.landlord.nid_verified = True
        self.landlord.save(update_fields=["nid_verified"])

        for room in (room_a, room_b):
            data = self._room_payload(room.pk)
            self.assertTrue(data["verified"], f"{room.title} should be verified")

    def test_saving_without_kyc_change_does_not_touch_rooms(self):
        """An unrelated profile save must not trigger the rooms update."""
        self._auth(self.landlord)
        room = self._publish_room()
        self.assertFalse(room.verified)

        self.landlord.phone = "01812345678"
        self.landlord.save(update_fields=["phone"])

        room.refresh_from_db()
        self.assertFalse(room.verified)

    def _make_roommate_profile(self, user, **overrides):
        self._auth(user)
        payload = {
            "budget_min": 8000,
            "budget_max": 15000,
            "preferred_area": "Mirpur",
            "room_type_pref": "studio",
            "gender_pref": "any",
            "lifestyle": ["clean", "student"],
            "occupation": "Engineer",
            "bio": "Looking for a tidy flatmate.",
            "move_in_date": "2026-09-01",
            "is_looking": True,
            **overrides,
        }
        res = self.client.put("/api/v1/roommates/profile/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        return res.data

    def test_roommate_matches_expose_kyc_state(self):
        """Match payloads carry nid_verified so verified users stand out."""
        verified_owner = User.objects.create_user(
            username="verified_owner",
            email="verified_owner@example.com",
            password="test12345",
            nid_verified=True,
        )
        unverified_owner = User.objects.create_user(
            username="unverified_owner",
            email="unverified_owner@example.com",
            password="test12345",
            nid_verified=False,
        )
        seeker = User.objects.create_user(
            username="seeker",
            email="seeker@example.com",
            password="test12345",
        )

        self._make_roommate_profile(verified_owner)
        self._make_roommate_profile(unverified_owner)
        self._make_roommate_profile(
            seeker,
            preferred_area="Mirpur",
            occupation="Student",
        )

        # The seeker asks for matches — both candidates are eligible.
        self._auth(seeker)
        res = self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(len(res.data), 2)

        by_username = {m["profile"]["user"]["username"]: m["profile"]["user"] for m in res.data}
        self.assertTrue(by_username["verified_owner"]["nid_verified"])
        self.assertFalse(by_username["unverified_owner"]["nid_verified"])
