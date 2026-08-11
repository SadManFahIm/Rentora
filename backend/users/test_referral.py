"""Tests for the referral program (Phase 10)."""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {"auth": "1000/hour"},
        "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
    }
)
class ReferralTests(APITestCase):
    def setUp(self):
        self.referrer = User.objects.create_user(
            username="referrer", email="referrer@example.com", password="test12345"
        )
        self.client.force_authenticate(self.referrer)

    def _register(self, ref=None):
        payload = {
            "username": "invitee",
            "email": "invitee@example.com",
            "password1": "demo12345",
            "password2": "demo12345",
            "name": "Invitee",
            "role": "tenant",
        }
        if ref:
            payload["ref"] = ref
        self.client.force_authenticate(None)
        return self.client.post("/api/v1/auth/register/", payload, format="json")

    def test_register_with_valid_ref_links_referrer(self):
        res = self._register(ref=self.referrer.referral_code)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        invitee = User.objects.get(username="invitee")
        self.assertEqual(invitee.referred_by, self.referrer)

    def test_register_with_unknown_ref_still_works(self):
        res = self._register(ref="ZZZZZZZZ")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertIsNone(User.objects.get(username="invitee").referred_by)

    def test_register_without_ref_links_nothing(self):
        res = self._register()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertIsNone(User.objects.get(username="invitee").referred_by)

    def test_referral_endpoint_returns_code_link_and_stats(self):
        self.client.force_authenticate(self.referrer)
        res = self.client.get("/api/v1/users/referral/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["code"], self.referrer.referral_code)
        self.assertIn(f"ref={self.referrer.referral_code}", res.data["link"])
        self.assertEqual(res.data["invited_count"], 0)
        self.assertEqual(res.data["invited"], [])

    def test_every_user_gets_a_unique_code(self):
        users = [
            User.objects.create_user(
                username=f"u{i}", email=f"u{i}@example.com", password="x1234567"
            )
            for i in range(3)
        ]
        codes = [u.referral_code for u in users]
        self.assertEqual(len(set(codes)), 3)
        self.assertTrue(all(codes))
