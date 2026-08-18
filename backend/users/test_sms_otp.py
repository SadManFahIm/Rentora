"""Tests for phone (SMS) OTP login (Phase 13).

Covers the full lifecycle: feature gating, code delivery, verification,
attempt limiting, cooldown, expiry, auto-registration of new phones, phone
number validation, and both the console and http SMS providers.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import SmsOtpChallenge

User = get_user_model()

REQUEST_URL = "/api/v1/auth/sms/request/"
VERIFY_URL = "/api/v1/auth/sms/verify/"

# Raised auth throttle so the suite is deterministic; keep the envelope
# handler so error shapes match prod (mirrors users/test_otp.py).
REST_OVERRIDE = {
    "DEFAULT_THROTTLE_RATES": {"auth": "1000/hour"},
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}


@override_settings(
    REST_FRAMEWORK=REST_OVERRIDE,
    SMS_OTP_ENABLED=True,
    SMS_PROVIDER="console",
    SMS_OTP_MAX_ATTEMPTS=3,
    SMS_OTP_RESEND_COOLDOWN_SECONDS=0,
)
class SmsOtpFlowTests(APITestCase):
    def setUp(self):
        # Capture codes at delivery time (the DB stores only their hash).
        self.sent_codes: list[str] = []
        self._send_patcher = patch(
            "users.sms.send_sms",
            side_effect=lambda phone, code: self.sent_codes.append(code),
        )
        self.addCleanup(self._send_patcher.stop)
        self._send_patcher.start()

    def _request(self, phone):
        return self.client.post(REQUEST_URL, {"phone": phone}, format="json")

    def _verify(self, phone, code):
        return self.client.post(VERIFY_URL, {"phone": phone, "code": code}, format="json")

    @override_settings(SMS_OTP_ENABLED=False)
    def test_feature_disabled_returns_503(self):
        res = self._request("01712345678")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("sms_disabled", res.data.get("errors", []))
        res = self._verify("01712345678", "123456")
        self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_request_sends_code_and_masks_phone(self):
        res = self._request("01712345678")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["phone_masked"], "+8801••••78")
        self.assertEqual(len(self.sent_codes), 1)
        self.assertEqual(len(self.sent_codes[0]), 6)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_request_accepts_common_bd_formats(self):
        for raw in ["01712345678", "8801712345678", "+8801712345678", "017-1234-5678"]:
            res = self._request(raw)
            self.assertEqual(res.status_code, status.HTTP_200_OK, msg=raw)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_request_rejects_invalid_numbers(self):
        for raw in ["12345", "0171234", "0161234567", "12345678901", "abc"]:
            res = self._request(raw)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=raw)

    def test_verify_correct_code_signs_in_existing_user(self):
        self.user = User.objects.create_user(username="sms.user", phone="+8801712345678")
        self._request("01712345678")
        res = self._verify("01712345678", self.sent_codes[-1])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["pk"], self.user.pk)
        challenge = SmsOtpChallenge.objects.get(phone="+8801712345678")
        self.assertEqual(challenge.status, SmsOtpChallenge.Status.USED)

    def test_verify_correct_code_auto_registers_new_phone(self):
        self._request("01711111111")
        self.assertFalse(User.objects.filter(phone="+8801711111111").exists())
        res = self._verify("01711111111", self.sent_codes[-1])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        created = User.objects.get(phone="+8801711111111")
        self.assertIn("bd17", created.username)
        self.assertEqual(created.role, User.Role.TENANT)

    def test_wrong_code_reports_remaining_attempts(self):
        self._request("01712345678")
        res = self._verify("01712345678", "000000")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("2 attempt(s)", res.data["message"])

    def test_lockout_after_max_attempts(self):
        self._request("01712345678")
        for _ in range(3):
            self._verify("01712345678", "000000")
        challenge = SmsOtpChallenge.objects.get(phone="+8801712345678")
        self.assertEqual(challenge.status, SmsOtpChallenge.Status.LOCKED)
        res = self._verify("01712345678", "000000")
        self.assertIn("Too many", res.data["message"])

    @override_settings(SMS_OTP_RESEND_COOLDOWN_SECONDS=30)
    def test_cooldown_blocks_re_request(self):
        self._request("01712345678")
        res = self._request("01712345678")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resend_blocked", res.data.get("errors", []))

    def test_expired_code_is_rejected(self):
        self._request("01712345678")
        challenge = SmsOtpChallenge.objects.get(phone="+8801712345678")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        res = self._verify("01712345678", self.sent_codes[-1])
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", res.data["message"])

    @override_settings(
        SMS_PROVIDER="http",
        SMS_GATEWAY_URL="https://sms.example.com/send",
    )
    def test_http_provider_posts_to_gateway(self):
        # Let the real send_sms run (HttpSmsProvider → requests.post).
        self._send_patcher.stop()
        with patch("requests.post") as mock_post:
            mock_post.return_value.raise_for_status.return_value = None
            self._request("01712345678")
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], "+8801712345678")
        self.assertEqual(payload["sender_id"], "")
        self.assertEqual(
            len(payload["message"]),
            len("Your Rentora verification code is XXXXXX. It expires in 10 minutes."),
        )

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_code_not_requested_yet_rejected(self):
        res = self._verify("01712345678", "123456")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("request a code first", res.data["message"])

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_invalid_code_shape_rejected_by_serializer(self):
        res = self._verify("01712345678", "abc123")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(REST_FRAMEWORK=REST_OVERRIDE)
    def test_phone_normalized_to_e164_in_db(self):
        self._request("017-1234-5678")
        self.assertTrue(SmsOtpChallenge.objects.filter(phone="+8801712345678").exists())
