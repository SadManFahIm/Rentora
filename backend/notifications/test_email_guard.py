"""Tests for the rate-limited alert email sender (notifications.email_guard)."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from notifications.email_guard import send_alert_email
from notifications.models import EmailDeliveryLog

User = get_user_model()


class SendAlertEmailTests(TestCase):
    """Daily budget + exponential failure backoff, all logged to the ledger."""

    EMAIL = "admin@example.com"
    TEMPLATE = "kyc_sla_alert"
    CONTEXT = {
        "user": None,  # replaced with a real user in setUp
        "title": "KYC queue breach",
        "message": "Queue is backed up.",
    }

    def setUp(self):
        self.user = User.objects.create_user(
            username="guard_admin",
            email=self.EMAIL,
            password="test12345",
        )
        self.CONTEXT = {**self.CONTEXT, "user": self.user}

    def _send(self, **kwargs):
        return send_alert_email(
            subject="[Rentora] KYC queue breach",
            to_email=self.EMAIL,
            template_name=self.TEMPLATE,
            context=self.CONTEXT,
            **kwargs,
        )

    def test_sends_and_records_success(self):
        log = self._send()
        self.assertEqual(log.status, EmailDeliveryLog.Status.SENT)
        self.assertEqual(log.attempt, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailDeliveryLog.objects.filter(status="sent").count(), 1)

    def test_daily_budget_skips_without_sending(self):
        with override_settings(ALERT_EMAIL_DAILY_BUDGET=1):
            first = self._send()
            second = self._send()
        self.assertEqual(first.status, EmailDeliveryLog.Status.SENT)
        self.assertEqual(second.status, EmailDeliveryLog.Status.SKIPPED)
        self.assertIn("daily budget", second.error)
        # Only the successful send actually hit the mail backend.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailDeliveryLog.objects.filter(status="skipped").count(), 1)

    def test_failed_send_is_logged_and_held_in_backoff(self):
        base = timezone.now()
        with (
            patch("django.utils.timezone.now", return_value=base),
            patch("notifications.email_guard.send_html_email", return_value=0),
        ):
            failed = self._send()
        self.assertEqual(failed.status, EmailDeliveryLog.Status.FAILED)
        self.assertEqual(len(mail.outbox), 0)

        # Within the 24h window the recipient is not retried.
        with (
            patch("django.utils.timezone.now", return_value=base + timedelta(hours=1)),
            patch("notifications.email_guard.send_html_email") as mock_send,
        ):
            held = self._send()
        self.assertEqual(held.status, EmailDeliveryLog.Status.SKIPPED)
        self.assertIn("backoff until", held.error)
        self.assertIn("1 consecutive failure", held.error)
        mock_send.assert_not_called()

        # After the window the retry is attempted again.
        with (
            patch("django.utils.timezone.now", return_value=base + timedelta(hours=25)),
            patch("notifications.email_guard.send_html_email", return_value=1) as mock_send,
        ):
            retried = self._send()
        self.assertEqual(retried.status, EmailDeliveryLog.Status.SENT)
        mock_send.assert_called_once()

    def test_backoff_doubles_per_consecutive_failure(self):
        base = timezone.now()
        # Two failures, one day apart (each after the previous window).
        for hours in (0, 25):
            with (
                patch("django.utils.timezone.now", return_value=base + timedelta(hours=hours)),
                patch("notifications.email_guard.send_html_email", return_value=0),
            ):
                self._send()
        # Two consecutive failures -> 48h window: a retry at +26h is still held.
        with (
            patch("django.utils.timezone.now", return_value=base + timedelta(hours=26)),
            patch("notifications.email_guard.send_html_email") as mock_send,
        ):
            held = self._send()
        self.assertEqual(held.status, EmailDeliveryLog.Status.SKIPPED)
        self.assertIn("2 consecutive failure", held.error)
        mock_send.assert_not_called()
        # ...but a retry at +74h (past the 48h window from the second
        # failure at +25h) goes through.
        with (
            patch("django.utils.timezone.now", return_value=base + timedelta(hours=74)),
            patch("notifications.email_guard.send_html_email", return_value=1) as mock_send,
        ):
            retried = self._send()
        self.assertEqual(retried.status, EmailDeliveryLog.Status.SENT)
        mock_send.assert_called_once()

    def test_empty_recipient_is_skipped(self):
        log = send_alert_email(
            subject="x",
            to_email="",
            template_name=self.TEMPLATE,
        )
        self.assertEqual(log.status, EmailDeliveryLog.Status.SKIPPED)
        self.assertIn("empty recipient", log.error)
        self.assertEqual(len(mail.outbox), 0)
