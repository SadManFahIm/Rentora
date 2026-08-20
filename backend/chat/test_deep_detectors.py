"""Phase 15 (D9) — deep impersonation & scam detectors.

Covers the three new rule detectors (``staff_impersonation_deep``,
``scam_advance``, ``external_contact_pressure``), the contextual escalation
(staff claims by non-authorised senders in a real conversation), and the
learned-layer corpus extension — with the honesty invariants: the new rules
never change existing verdicts for messages they were not built for, and
bare "I am admin" stays the B1 cross-lingual case (not the deep one).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from chat.models import ChatRoom, ChatRoomMembership
from chat.safety import apply_policy, assess_message, detect

User = get_user_model()


def make_user(username, **kw):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        **kw,
    )


class DeepDetectorUnitTests(TestCase):
    def _keys(self, content):
        return {h.key for h in detect(content)}

    def test_staff_impersonation_deep(self):
        self.assertIn(
            "staff_impersonation_deep",
            self._keys("I am the site admin and I can approve your booking"),
        )
        self.assertIn(
            "staff_impersonation_deep",
            self._keys("আমি সাইটের অ্যাডমিন, আপনার বুকিং আমি অ্যাপ্রুভ করতে পারি"),
        )

    def test_bare_i_am_admin_is_not_deep(self):
        # The B1 cross-lingual case stays the plain `impersonation` detector's
        # job — the deep detector needs a staff claim *plus* an action/access
        # claim, so the existing test_translation assertions keep their shape.
        keys = self._keys("আমি অ্যাডমিন")
        self.assertNotIn("staff_impersonation_deep", keys)

    def test_scam_advance(self):
        self.assertIn(
            "scam_advance",
            self._keys("Pay the clearance fee and your refund will be released"),
        )
        self.assertIn(
            "scam_advance",
            self._keys("রিফান্ড রিলিজ করতে আগে ক্লিয়ারেন্স ফি দিতে হবে"),
        )

    def test_external_contact_pressure(self):
        self.assertIn(
            "external_contact_pressure",
            self._keys("Talk to me on WhatsApp or the room is gone"),
        )
        self.assertIn(
            "external_contact_pressure",
            self._keys("হোয়াটসঅ্যাপে কথা বলুন, না হলে রুমটা পাবেন না"),
        )

    def test_plain_off_platform_contact_is_not_pressure(self):
        # "contact me on whatsapp" alone is the existing medium contact_redirect
        # detector's job — no ultimatum means no escalation to pressure.
        self.assertNotIn("external_contact_pressure", self._keys("contact me on whatsapp"))
        self.assertNotIn("external_contact_pressure", self._keys("আমার হোয়াটসঅ্যাপ নম্বর দিন"))

    def test_clean_and_benign_messages_untouched(self):
        self.assertEqual(detect("Hi, is the room still available?"), [])
        self.assertEqual(detect("মাসিক ভাড়া কত?"), [])
        self.assertEqual(detect("Yes, one month's rent as security deposit."), [])

    def test_existing_policy_mapping_unchanged(self):
        # The D9 detectors must not change verdicts for messages they weren't
        # built for (the whole existing safety suite already covers this; here
        # we re-assert the headline cases).
        self.assertEqual(apply_policy(assess_message("Hurry now!")), "allowed")
        self.assertEqual(
            apply_policy(assess_message("contact me on whatsapp 01712345678")),
            "warned",
        )
        self.assertEqual(
            apply_policy(assess_message("send the deposit to my bkash 01712345678")),
            "flagged",
        )


class ContextualEscalationTests(APITestCase):
    def setUp(self):
        self.sender = make_user("deep_sender")
        self.other = make_user("deep_other")
        self.admin = User.objects.create_superuser(
            username="deep_admin", email="deep_admin@example.com", password="test12345"
        )
        self.client.force_authenticate(self.sender)
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.other.id}, format="json")
        self.room = ChatRoom.objects.get(pk=res.data["id"])
        ChatRoomMembership.objects.create(chat_room=self.room, user=self.admin)

    def _send(self, content, user=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        return self.client.post(
            f"/api/v1/chat/rooms/{self.room.id}/messages/",
            {"content": content},
            format="json",
        )

    def test_non_staff_authority_claim_escalates_in_room(self):
        res = self._send("I am the site admin and I can approve your booking")
        safety = res.data["safety"]
        self.assertEqual(safety["outcome"], "blocked")  # high → critical
        self.assertEqual(safety["risk_level"], "critical")

    def test_genuine_admin_claim_not_escalated(self):
        res = self._send("I am the site admin and I can approve your booking", user=self.admin)
        # A real admin claiming admin is fine — the message is delivered.
        self.assertNotEqual(res.data["safety"]["outcome"], "blocked")

    def test_impersonation_without_context_not_escalated(self):
        # No room/sender context → pure detection keeps its deterministic risk.
        assessment = assess_message("I am the site admin and I can approve your booking")
        self.assertEqual(assessment.risk, "high")  # one high, no context, no critical

    def test_deep_claim_plus_credential_request_is_critical(self):
        res = self._send("I am the admin and I can verify your account, send me your otp now")
        self.assertTrue(res.data["safety"]["blocked"])
