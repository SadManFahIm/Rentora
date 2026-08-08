"""Tests for email-OTP two-factor authentication.

Covers the complete challenge lifecycle: login intercept, code delivery,
verification, resend, attempt limiting, expiry, and the enable/disable
toggle (including the password guard on enabling).
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import OTPChallenge
from .services import OTP_MAX_ATTEMPTS

User = get_user_model()

LOGIN_URL = "/api/v1/auth/login/"
VERIFY_URL = "/api/v1/auth/otp/verify/"
RESEND_URL = "/api/v1/auth/otp/resend/"
TOGGLE_URL = "/api/v1/auth/otp/toggle/"

# Raised auth throttle (10/hour per IP is the default) so the suite is
# deterministic; keep the envelope handler so error shapes match prod.
REST_OVERRIDE = {
    "DEFAULT_THROTTLE_RATES": {"auth": "1000/hour"},
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}


class OTPFlowTests(APITestCase):
    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def setUp(self):
        self.user = User.objects.create_user(
            username="otp.user",
            email="otp.user@rentora.com",
            password="demo12345",
        )
        # Capture the code at delivery time (the DB stores only its hash).
        self.delivered_codes: list[str] = []
        patcher = patch(
            "users.services._deliver_code",
            side_effect=lambda user, code: self.delivered_codes.append(code),
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def _login(self):
        return self.client.post(
            LOGIN_URL,
            {"username": "otp.user", "password": "demo12345"},
            format="json",
        )

    def _enable(self):
        self.user.otp_enabled = True
        self.user.save(update_fields=["otp_enabled"])

    def _verify(self, challenge, code):
        return self.client.post(VERIFY_URL, {"challenge": challenge, "code": code}, format="json")

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_login_without_2fa_returns_tokens_directly(self):
        res = self._login()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["email"], "otp.user@rentora.com")

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_login_with_2fa_returns_pending_challenge_not_tokens(self):
        self._enable()
        res = self._login()
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(res.data["otp_required"])
        self.assertTrue(res.data["challenge"])
        # The destination is masked — never the full address in the body.
        self.assertEqual(res.data["destination_masked"], "o***@rentora.com")
        self.assertEqual(res.data["expires_in"], 600)
        # No tokens are issued at this stage.
        self.assertNotIn("access", res.data)
        # The code was actually delivered (email side effect).
        self.assertEqual(len(self.delivered_codes), 1)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_verify_with_correct_code_returns_tokens(self):
        self._enable()
        challenge = self._login().data["challenge"]
        code = self.delivered_codes[-1]

        res = self._verify(challenge, code)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertEqual(res.data["user"]["email"], "otp.user@rentora.com")

        # The challenge is single-use.
        res2 = self._verify(challenge, code)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_wrong_code_increments_attempts_then_locks(self):
        self._enable()
        challenge = self._login().data["challenge"]

        for i in range(OTP_MAX_ATTEMPTS):
            res = self._verify(challenge, "000000")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            if i < OTP_MAX_ATTEMPTS - 1:
                self.assertIn("attempt(s) remaining", res.data["message"])

        # Locked — even the real code is now refused.
        res = self._verify(challenge, self.delivered_codes[-1])
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Too many incorrect attempts", res.data["message"])
        self.assertEqual(
            OTPChallenge.objects.get(user=self.user).status, OTPChallenge.Status.LOCKED
        )

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_expired_challenge_is_rejected(self):
        self._enable()
        challenge = self._login().data["challenge"]
        OTPChallenge.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        res = self._verify(challenge, self.delivered_codes[-1])
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", res.data["message"])

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_unknown_challenge_is_rejected(self):
        res = self._verify("bogus-token", "123456")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE, OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_resend_issues_a_fresh_code(self):
        self._enable()
        challenge = self._login().data["challenge"]
        first_code = self.delivered_codes[-1]

        res = self.client.post(RESEND_URL, {"challenge": challenge}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.delivered_codes), 2)
        new_code = self.delivered_codes[-1]
        self.assertNotEqual(first_code, new_code)

        # The fresh code verifies; the old one no longer does.
        self.assertEqual(self._verify(challenge, new_code).status_code, status.HTTP_200_OK)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_toggle_requires_current_password_to_enable(self):
        self.client.force_authenticate(user=self.user)

        res = self.client.post(TOGGLE_URL, {"enable": True, "password": "wrong"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.get(pk=self.user.pk).otp_enabled)

        res = self.client.post(TOGGLE_URL, {"enable": True, "password": "demo12345"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["otp_enabled"])
        self.assertTrue(User.objects.get(pk=self.user.pk).otp_enabled)

        # Disabling requires no password (it only weakens security).
        res = self.client.post(TOGGLE_URL, {"enable": False}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.get(pk=self.user.pk).otp_enabled)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_toggle_requires_an_email_address(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])
        self.client.force_authenticate(user=self.user)

        res = self.client.post(TOGGLE_URL, {"enable": True, "password": "demo12345"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.get(pk=self.user.pk).otp_enabled)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_stale_challenge_is_invalidated_on_new_login(self):
        self._enable()
        old_challenge = self._login().data["challenge"]
        # A fresh login invalidates the previous pending challenge.
        self._login()

        challenges = list(OTPChallenge.objects.filter(user=self.user).order_by("created_at"))
        self.assertEqual(len(challenges), 2)
        self.assertEqual(challenges[0].status, OTPChallenge.Status.EXPIRED)  # stale
        self.assertEqual(challenges[1].status, OTPChallenge.Status.PENDING)  # live

        # The stale challenge can no longer complete the sign-in.
        res = self._verify(old_challenge, self.delivered_codes[0])
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", res.data["message"])
