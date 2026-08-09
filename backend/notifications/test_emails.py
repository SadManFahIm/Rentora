"""Tests for the transactional email helper (notifications.emails)."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from notifications.emails import send_html_email
from rooms import models as rooms_models

User = get_user_model()


class SendHtmlEmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tenant", email="tenant@example.com", password="test12345"
        )
        self.room = rooms_models.Room.objects.create(
            owner=self.user,
            title="Modern Studio, Mirpur",
            description="Bright studio.",
            room_type="studio",
            price=13500,
            area="Mirpur",
            address="12 Mirpur Road",
            lat=23.8069,
            lng=90.3687,
            amenities=["wifi"],
            size_sqft=420,
        )

    def test_sends_multipart_message_with_html_alternative(self):
        sent = send_html_email(
            subject="Hello",
            to_email="tenant@example.com",
            template_name="otp_code",
            context={"user": self.user, "code": "123456", "expires_in_minutes": 10},
        )
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Hello")
        self.assertEqual(message.to, ["tenant@example.com"])
        # Plain-text fallback body present…
        self.assertIn("123456", message.body)
        # …and the HTML alternative is attached.
        alternatives = {mime: content for content, mime in message.alternatives}
        self.assertIn("text/html", alternatives)
        self.assertIn("123456", alternatives["text/html"])
        self.assertIn("Rentora", alternatives["text/html"])

    def test_empty_recipient_is_a_noop(self):
        sent = send_html_email(
            subject="Skip me",
            to_email="",
            template_name="otp_code",
            context={"user": self.user, "code": "123456", "expires_in_minutes": 10},
        )
        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_recovery_codes_template_renders_all_codes(self):
        codes = ["ABCD-EFGH-1234", "WXYZ-0000-9999"]
        sent = send_html_email(
            subject="Backup codes",
            to_email="a@b.com",
            template_name="recovery_codes",
            context={"user": self.user, "recovery_codes": codes},
        )
        self.assertEqual(sent, 1)
        alternatives = {mime: content for content, mime in mail.outbox[0].alternatives}
        html = alternatives["text/html"]
        for code in codes:
            self.assertIn(code, html)

    def test_booking_template_renders_room_details(self):
        sent = send_html_email(
            subject="Booking approved",
            to_email="t@e.com",
            template_name="booking_status",
            context={
                "user": self.user,
                "headline": "Your booking was approved",
                "body": "Great news!",
                "room": self.room,
                "action_url": "/dashboard",
            },
        )
        self.assertEqual(sent, 1)
        alternatives = {mime: content for content, mime in mail.outbox[0].alternatives}
        html = alternatives["text/html"]
        self.assertIn("Your booking was approved", html)
        self.assertIn("Modern Studio, Mirpur", html)
