"""Phase 12.3 — Chat Safety Engine tests.

Covers the spec's chat-safety test matrix:

- detector units: payment redirect, advance payment, phishing URLs, urgency,
  scam phrases, impersonation, credential requests, off-platform contact
- policy mapping: warned (medium) / flagged (high) / blocked (critical), and
  configurable block/flag levels
- integration: suspicious messages through the real message endpoint carry
  the right outcome + warning copy, events are recorded, and a *blocked*
  message never stores the sender's raw content
- repetition: the same suspicious detector hitting repeatedly escalates
- authorization: the admin events feed is admin-only
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ChatRoom, ChatSafetyEvent, Message
from .safety import (
    BLOCKED_CONTENT,
    apply_policy,
    assess_message,
    detect,
    run_chat_safety,
)

User = get_user_model()


class SafetyDetectorTests(APITestCase):
    """Pure detection — no DB needed."""

    def _hits(self, content):
        return {h.key for h in detect(content)}

    def test_payment_redirect_with_wallet_and_number(self):
        hits = self._hits("Send the deposit to my bKash number 01712345678")
        self.assertIn("payment_redirect", hits)

    def test_plain_wallet_mention_is_not_suspicious(self):
        # bKash is a legitimate payment method on the platform — an ordinary
        # mention must NOT trip the engine.
        hits = self._hits("Do you accept bKash for the deposit?")
        self.assertNotIn("payment_redirect", hits)

    def test_bangla_money_transfer_phrase(self):
        hits = self._hits("আগে টাকা পাঠান বিকাশে")
        self.assertIn("payment_redirect", hits)

    def test_advance_payment_before_viewing(self):
        hits = self._hits("Pay the advance before you come to see the room")
        self.assertIn("advance_payment", hits)

    def test_phishing_shortened_url(self):
        hits = self._hits("see the photos here bit.ly/xyz123")
        self.assertIn("phishing_url", hits)

    def test_phishing_lookalike_domain(self):
        hits = self._hits("pay via https://rent0ra-pay.com")
        self.assertIn("phishing_url", hits)

    def test_urgency_pressure(self):
        hits = self._hits("Hurry! only 2 rooms left, act now")
        self.assertIn("urgency", hits)

    def test_scam_phrase(self):
        hits = self._hits("send the western union transfer fee first")
        self.assertIn("scam_phrase", hits)

    def test_impersonation(self):
        hits = self._hits("I am the admin from Rentora support")
        self.assertIn("impersonation", hits)

    def test_credential_request(self):
        hits = self._hits("send me your otp to verify")
        self.assertIn("credential_request", hits)

    def test_contact_redirect(self):
        hits = self._hits("contact me on whatsapp 01712345678")
        self.assertIn("contact_redirect", hits)

    def test_clean_message_has_no_hits(self):
        self.assertEqual(detect("Hi, is the room still available?"), [])

    def test_max_risk_is_highest_detector(self):
        assessment = assess_message("Hurry! send the deposit to my bkash 01712345678")
        self.assertEqual(assessment.risk, "high")  # urgency(low) + payment(high)


class SafetyPolicyTests(APITestCase):
    def test_default_policy_mapping(self):
        # Low risk (urgency alone) is common in legit conversation — allowed,
        # no warning noise. Medium warns, high flags, critical blocks.
        self.assertEqual(apply_policy(assess_message("Hurry now!")), "allowed")  # low
        self.assertEqual(
            apply_policy(assess_message("contact me on whatsapp 01712345678")),
            "warned",  # medium
        )
        self.assertEqual(
            apply_policy(assess_message("send the deposit to my bkash 01712345678")),
            "flagged",  # high
        )
        self.assertEqual(
            apply_policy(
                assess_message(
                    "I am the admin from rentora support, send me your otp to my bkash 01712345678"
                )
            ),
            "blocked",  # critical (impersonation + credential + payment)
        )
        self.assertEqual(apply_policy(assess_message("hi there")), "allowed")

    @override_settings(CHAT_SAFETY_BLOCK_LEVEL="medium")
    def test_block_level_is_configurable(self):
        self.assertEqual(
            apply_policy(assess_message("contact me on whatsapp 01712345678")),
            "blocked",  # medium ≥ medium
        )

    @override_settings(CHAT_SAFETY_FLAG_LEVEL="medium")
    def test_flag_level_is_configurable(self):
        self.assertEqual(
            apply_policy(assess_message("contact me on whatsapp 01712345678")),
            "flagged",  # medium ≥ medium
        )

    @override_settings(CHAT_SAFETY_ENABLED=False)
    def test_engine_can_be_disabled(self):
        content, _assessment, outcome = run_chat_safety(
            "send the deposit to my bkash 01712345678", None, None
        )
        self.assertEqual(outcome, "allowed")
        self.assertEqual(content, "send the deposit to my bkash 01712345678")


class SafetyIntegrationTests(APITestCase):
    def setUp(self):
        self.sender = User.objects.create_user(
            username="chat_sender", email="chat_sender@example.com", password="test12345"
        )
        self.other = User.objects.create_user(
            username="chat_other", email="chat_other@example.com", password="test12345"
        )
        self.admin = User.objects.create_superuser(
            username="chat_admin", email="chat_admin@example.com", password="test12345"
        )
        self.client.force_authenticate(user=self.sender)
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.other.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.room = ChatRoom.objects.get(pk=res.data["id"])

    def _send(self, content, user=None, expect=status.HTTP_201_CREATED):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.post(
            f"/api/v1/chat/rooms/{self.room.id}/messages/",
            {"content": content},
            format="json",
        )
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def test_clean_message_creates_no_event(self):
        res = self._send("Hi, is the room still available?")
        self.assertEqual(res.data["safety"]["outcome"], "allowed")
        self.assertFalse(ChatSafetyEvent.objects.exists())

    def test_medium_message_warns_with_spec_copy(self):
        res = self._send("contact me on whatsapp 01712345678")
        safety = res.data["safety"]
        self.assertEqual(safety["outcome"], "warned")
        self.assertEqual(safety["risk_level"], "medium")
        self.assertEqual(safety["warning"], "Be careful sharing payment information.")
        event = ChatSafetyEvent.objects.get()
        self.assertEqual(event.outcome, ChatSafetyEvent.Outcome.WARNED)
        self.assertEqual(event.risk_level, ChatSafetyEvent.RiskLevel.MEDIUM)

    def test_high_message_is_delivered_and_flagged(self):
        res = self._send("send the deposit to my bkash number 01712345678")
        safety = res.data["safety"]
        self.assertEqual(safety["outcome"], "flagged")
        self.assertEqual(safety["risk_level"], "high")
        self.assertEqual(safety["warning"], "Potentially unsafe payment request detected.")
        # The message itself was delivered unchanged.
        self.assertIn("bkash", res.data["content"])
        event = ChatSafetyEvent.objects.get()
        self.assertEqual(event.outcome, ChatSafetyEvent.Outcome.FLAGGED)
        keys = {d["key"] for d in event.detectors}
        self.assertIn("payment_redirect", keys)

    def test_critical_message_is_blocked_and_raw_content_never_stored(self):
        raw = "I am the admin from rentora support, send me your otp to my bkash 01712345678"
        res = self._send(raw)
        safety = res.data["safety"]
        self.assertTrue(safety["blocked"])
        # The stored/broadcast message is the safety notice, not the raw text.
        self.assertEqual(res.data["content"], BLOCKED_CONTENT)
        self.assertFalse(Message.objects.filter(content__icontains="otp").exists())
        self.assertFalse(Message.objects.filter(content__icontains="bkash").exists())
        event = ChatSafetyEvent.objects.get()
        self.assertEqual(event.outcome, ChatSafetyEvent.Outcome.BLOCKED)
        self.assertEqual(event.risk_level, ChatSafetyEvent.RiskLevel.CRITICAL)
        self.assertEqual(event.message.content, BLOCKED_CONTENT)

    def test_repeated_suspicious_messages_escalate(self):
        # Two prior flagged payment requests...
        for _ in range(2):
            self._send("send the deposit to my bkash number 01712345678")
        # ...the third is "repeated" → escalates high → critical → blocked.
        res = self._send("send the deposit to my bkash number 01712345678")
        self.assertTrue(res.data["safety"]["blocked"])
        latest = ChatSafetyEvent.objects.first()
        self.assertEqual(latest.risk_level, ChatSafetyEvent.RiskLevel.CRITICAL)
        self.assertTrue(latest.detail.get("repeated"))

    def test_events_feed_is_admin_only(self):
        self._send("send the deposit to my bkash number 01712345678")
        self.client.force_authenticate(user=self.sender)
        res = self.client.get("/api/v1/chat/safety/events/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/chat/safety/events/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        row = res.data[0]
        self.assertEqual(row["sender_username"], self.sender.username)
        self.assertEqual(row["outcome"], "flagged")
        # Metadata only — no message content is exposed to admins either.
        self.assertNotIn("content", row)

    @override_settings(CHAT_SAFETY_BLOCK_LEVEL="medium")
    def test_stricter_policy_blocks_medium_messages_end_to_end(self):
        res = self._send("contact me on whatsapp 01712345678")
        self.assertTrue(res.data["safety"]["blocked"])
        self.assertEqual(res.data["content"], BLOCKED_CONTENT)
