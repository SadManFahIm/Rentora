"""Tests for WebAuthn / FIDO2 passkey registration and authentication.

The authenticator side of the ceremony cannot run in CI, so the
``py_webauthn`` *verification* functions are mocked to return verified
responses; challenge generation runs for real (it is pure). The tests pin
the contract of the four endpoints, the challenge lifecycle, and the
credential store.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import PasskeyCredential

User = get_user_model()

REG_BEGIN_URL = "/api/v1/auth/passkey/register/begin/"
REG_COMPLETE_URL = "/api/v1/auth/passkey/register/complete/"
LOGIN_BEGIN_URL = "/api/v1/auth/passkey/login/begin/"
LOGIN_COMPLETE_URL = "/api/v1/auth/passkey/login/complete/"

REST_OVERRIDE = {
    "DEFAULT_THROTTLE_RATES": {"auth": "1000/hour"},
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}

# A fake verified registration result.
FAKE_CRED_ID = b"\x01\x02\x03\x04\x05"
FAKE_PUBLIC_KEY = b"\xa5\x01\x02\x03"


def _fake_verified_registration():
    return SimpleNamespace(
        verified=True,
        credential_id=FAKE_CRED_ID,
        credential=SimpleNamespace(
            id=FAKE_CRED_ID,
            public_key=FAKE_PUBLIC_KEY,
            sign_count=1,
        ),
    )


class PasskeyRegistrationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="passkey.user",
            email="passkey.user@rentora.com",
            password="demo12345",
        )
        self.client.force_authenticate(user=self.user)

    def test_register_begin_requires_auth(self):
        self.client.logout()
        res = self.client.post(REG_BEGIN_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_register_begin_returns_options_payload(self):
        res = self.client.post(REG_BEGIN_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("rp", res.data)
        self.assertEqual(res.data["rp"]["id"], "localhost")
        self.assertIn("challenge", res.data)
        self.assertIn("user", res.data)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    @patch("users.passkey._wa_verify_reg_response", return_value=_fake_verified_registration())
    def test_register_complete_stores_the_public_key(self, mock_verify):
        res = self.client.post(
            REG_COMPLETE_URL,
            {
                "response": {
                    "id": "AQIDBAU",
                    "type": "public-key",
                    "response": {"transports": ["internal"]},
                },
                "name": "My laptop",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        cred = PasskeyCredential.objects.get(user=self.user)
        self.assertEqual(cred.credential_id, "AQIDBAU")
        self.assertEqual(cred.sign_count, 1)
        self.assertEqual(cred.name, "My laptop")

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    @patch(
        "users.passkey._wa_verify_reg_response",
        side_effect=Exception("Registration could not be verified."),
    )
    def test_register_complete_reports_failure(self, mock_verify):
        res = self.client.post(
            REG_COMPLETE_URL,
            {"response": {"id": "AQIDBAU"}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PasskeyCredential.objects.filter(user=self.user).count(), 0)


class PasskeyAuthenticationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="passkey.user",
            email="passkey.user@rentora.com",
            password="demo12345",
        )

    def _seed_credential(self, credential_id="AQIDBAU"):
        return PasskeyCredential.objects.create(
            user=self.user,
            credential_id=credential_id,
            public_key="AaBbCc",
            sign_count=1,
        )

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_login_begin_returns_options_and_challenge_id(self):
        res = self.client.post(LOGIN_BEGIN_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("challenge", res.data)
        self.assertIn("challenge_id", res.data)
        # Discoverable-credential flow: an empty allowCredentials list means
        # the browser offers any passkey for this RP (conditional UI).
        self.assertEqual(res.data["allowCredentials"], [])

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    @patch(
        "users.passkey._wa_verify_auth_response",
        return_value=SimpleNamespace(verified=True, new_sign_count=2),
    )
    def test_login_complete_issues_tokens_and_updates_counter(self, mock_verify):
        self._seed_credential()
        begin = self.client.post(LOGIN_BEGIN_URL, {}, format="json").data

        res = self.client.post(
            LOGIN_COMPLETE_URL,
            {
                "challenge_id": begin["challenge_id"],
                "response": {"id": "AQIDBAU", "type": "public-key"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["email"], "passkey.user@rentora.com")
        # The sign counter advanced (replay protection).
        self.assertEqual(PasskeyCredential.objects.get(user=self.user).sign_count, 2)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    @patch(
        "users.passkey._wa_verify_auth_response",
        side_effect=Exception("This passkey is not registered."),
    )
    def test_login_complete_rejects_unregistered_credential(self, mock_verify):
        begin = self.client.post(LOGIN_BEGIN_URL, {}, format="json").data
        res = self.client.post(
            LOGIN_COMPLETE_URL,
            {
                "challenge_id": begin["challenge_id"],
                "response": {"id": "Unregistered"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_login_complete_rejects_expired_challenge(self):
        self._seed_credential()
        res = self.client.post(
            LOGIN_COMPLETE_URL,
            {"challenge_id": "bogus-challenge", "response": {"id": "AQIDBAU"}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
