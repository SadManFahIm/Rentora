"""Tests for user registration — success, duplicate-email enforcement and
password-mismatch validation.

The register endpoint is throttled per IP (10/hour) via AuthRateThrottle, so
the auth scope is raised for this suite to keep tests deterministic.
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = "/api/v1/auth/register/"


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_RATES": {"auth": "1000/hour"},
        "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
    }
)
class RegisterEndpointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_user(
            username="existing.user",
            email="existing.user@rentora.com",
            password="demo12345",
        )

    def _register(self, payload):
        return self.client.post(REGISTER_URL, payload, format="json")

    def test_registration_succeeds_and_returns_jwt(self):
        res = self._register(
            {
                "username": "new.user",
                "email": "new.user@rentora.com",
                "password1": "demo12345",
                "password2": "demo12345",
                "name": "New User",
                "role": "tenant",
            }
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["email"], "new.user@rentora.com")
        # The user is persisted and usable for login.
        user = User.objects.get(username="new.user")
        self.assertTrue(user.check_password("demo12345"))
        self.assertEqual(user.role, "tenant")

    def test_duplicate_email_is_rejected(self):
        res = self._register(
            {
                "username": "someone.else",
                "email": "existing.user@rentora.com",
                "password1": "demo12345",
                "password2": "demo12345",
                "name": "Someone Else",
            }
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # The unified error envelope surfaces the readable reason.
        self.assertEqual(
            res.data["message"], "A user is already registered with this email address."
        )
        # No duplicate account may be created.
        self.assertFalse(User.objects.filter(username="someone.else").exists())

    def test_duplicate_username_is_rejected(self):
        res = self._register(
            {
                "username": "existing.user",
                "email": "brand.new@rentora.com",
                "password1": "demo12345",
                "password2": "demo12345",
                "name": "Brand New",
            }
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mismatched_passwords_are_rejected(self):
        res = self._register(
            {
                "username": "pw.mismatch",
                "email": "pw.mismatch@rentora.com",
                "password1": "demo12345",
                "password2": "different123",
                "name": "PW Mismatch",
            }
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="pw.mismatch").exists())

    def test_register_payload_defaults_to_tenant_role(self):
        res = self._register(
            {
                "username": "default.role",
                "email": "default.role@rentora.com",
                "password1": "demo12345",
                "password2": "demo12345",
                "name": "Default Role",
            }
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(username="default.role").role, "tenant")
