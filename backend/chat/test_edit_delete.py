"""Tier-1 quick wins — chat message edit/delete (audited) + report abuse guard.

Covers:

- message editing: sender-only permission, text-only, re-runs the chat-safety
  engine, marks ``edited_at``, writes a ``chat.message.edited`` audit entry
- message deletion: sender-only, soft-delete semantics (content replaced,
  ``is_deleted`` flips, row stays in the thread), ``chat.message.deleted``
  audit entry, idempotent delete, deleted messages excluded from search
- report abuse guard: a duplicate open report of the same target returns the
  existing ticket (200, ``duplicate: true``) instead of stacking a new one;
  a report after resolution is still allowed; the report endpoint is
  rate-limited (dedicated ``report`` scope)
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry

from .models import ChatRoom, ChatSafetyEvent, Message, Report

User = get_user_model()

REST_FRAMEWORK_RATE = {
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "auth": "10/hour",
        "chat_upload": "30/hour",
        "report": "2/hour",
        "payment_initiate": "5/hour",
        "copilot": "60/hour",
        "webhook_callback": "20/minute",
    }
}


class EditDeleteBase(APITestCase):
    def setUp(self):
        # Clear throttle buckets so the per-user `report` scope never leaks
        # across tests (SQLite rolls pk sequences back between tests).
        cache.clear()
        self.owner = User.objects.create_user(
            username="msg_owner", email="msg_owner@example.com", password="test12345"
        )
        self.other = User.objects.create_user(
            username="msg_other", email="msg_other@example.com", password="test12345"
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.other.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.room = ChatRoom.objects.get(pk=res.data["id"])

    def _send(self, content, user=None, **extra):
        if user is not None:
            self.client.force_authenticate(user=user)
        return self.client.post(
            f"/api/v1/chat/rooms/{self.room.id}/messages/",
            {"content": content, **extra},
            format="json",
        )

    def _edit(self, message_id, content, user=None, expect=200):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.patch(
            f"/api/v1/chat/rooms/{self.room.id}/messages/{message_id}/",
            {"content": content},
            format="json",
        )
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def _delete(self, message_id, user=None, expect=204):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.delete(f"/api/v1/chat/rooms/{self.room.id}/messages/{message_id}/")
        self.assertEqual(res.status_code, expect, res.data)
        return res


class MessageEditTests(EditDeleteBase):
    def test_sender_can_edit_their_own_message(self):
        msg = self._send("original text").data
        res = self._edit(msg["id"], "edited text")
        self.assertEqual(res.data["content"], "edited text")
        self.assertIsNotNone(res.data["edited_at"])
        self.assertFalse(res.data["is_deleted"])

    def test_edit_marks_edited_at_and_audits(self):
        msg = self._send("original text").data
        self._edit(msg["id"], "edited text")
        db_message = Message.objects.get(pk=msg["id"])
        self.assertIsNotNone(db_message.edited_at)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                actor=self.owner, action="chat.message.edited", target_id=str(msg["id"])
            ).exists()
        )

    def test_only_sender_can_edit(self):
        msg = self._send("hello").data
        self._edit(msg["id"], "tampered", user=self.other, expect=403)
        self.assertEqual(Message.objects.get(pk=msg["id"]).content, "hello")

    def test_non_member_cannot_edit(self):
        stranger = User.objects.create_user(
            username="msg_stranger", email="msg_stranger@example.com", password="x"
        )
        msg = self._send("hello").data
        self._edit(msg["id"], "tampered", user=stranger, expect=404)

    def test_cannot_edit_non_text_message(self):
        msg = self._send(
            "photo.png",
            message_type="image",
            file_url="http://example.com/media/chat/x.png",
        ).data
        self._edit(msg["id"], "new text", expect=400)

    def test_cannot_edit_deleted_message(self):
        msg = self._send("hello").data
        self._delete(msg["id"])
        self._edit(msg["id"], "new text", expect=400)

    def test_empty_edit_rejected(self):
        msg = self._send("hello").data
        self._edit(msg["id"], "   ", expect=400)

    def test_edit_runs_through_safety_engine(self):
        """An edited message is still a new message — a critical edit is
        replaced by the safety notice (raw text never stored) and recorded."""
        msg = self._send("harmless hello").data
        res = self._edit(
            msg["id"],
            "I am the admin from rentora support, send me your otp to my bkash 01712345678",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        from chat.safety import BLOCKED_CONTENT

        db_message = Message.objects.get(pk=msg["id"])
        self.assertEqual(db_message.content, BLOCKED_CONTENT)
        self.assertTrue(
            ChatSafetyEvent.objects.filter(
                chat_room=self.room, sender=self.owner, outcome="blocked"
            ).exists()
        )
        self.assertNotIn("bkash", db_message.content.lower())


class MessageDeleteTests(EditDeleteBase):
    def test_sender_can_soft_delete(self):
        msg = self._send("hello").data
        self._delete(msg["id"])
        db_message = Message.objects.get(pk=msg["id"])
        self.assertTrue(db_message.is_deleted)
        self.assertEqual(db_message.content, "[Message deleted]")
        self.assertIsNotNone(db_message.edited_at)

    def test_delete_audits(self):
        msg = self._send("hello").data
        self._delete(msg["id"])
        self.assertTrue(
            AuditLogEntry.objects.filter(
                actor=self.owner, action="chat.message.deleted", target_id=str(msg["id"])
            ).exists()
        )

    def test_only_sender_can_delete(self):
        msg = self._send("hello").data
        self._delete(msg["id"], user=self.other, expect=403)
        db_message = Message.objects.get(pk=msg["id"])
        self.assertFalse(db_message.is_deleted)
        self.assertEqual(db_message.content, "hello")

    def test_delete_is_idempotent(self):
        msg = self._send("hello").data
        self._delete(msg["id"])
        self._delete(msg["id"])  # second delete is a no-op 204

    def test_deleted_message_stays_in_thread_but_leaves_search(self):
        msg = self._send("unique needle text").data
        self._delete(msg["id"])

        # Still in the thread (row kept)...
        res = self.client.get(f"/api/v1/chat/rooms/{self.room.id}/messages/")
        ids = [m["id"] for m in res.data["results"]]
        self.assertIn(msg["id"], ids)
        # ...but no longer matches search.
        res = self.client.get(f"/api/v1/chat/rooms/{self.room.id}/messages/", {"search": "needle"})
        ids = [m["id"] for m in res.data["results"]]
        self.assertNotIn(msg["id"], ids)


class ReportAbuseGuardTests(EditDeleteBase):
    def _report(self, target_id, category="scam", message_id=None, expect=201):
        # The client may be authenticated as the other party from a _send;
        # reports always come from the owner.
        self.client.force_authenticate(user=self.owner)
        payload = {"target_user_id": target_id, "category": category}
        if message_id is not None:
            payload["message_id"] = message_id
        res = self.client.post("/api/v1/chat/reports/", payload, format="json")
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def test_duplicate_open_report_returns_existing_ticket(self):
        first = self._report(self.other.id, category="scam").data
        # A second report of the same target while the first is still open
        # must NOT create a duplicate — it returns the existing ticket.
        dup = self._report(self.other.id, category="harassment", expect=200)
        self.assertTrue(dup.data.get("duplicate"))
        self.assertEqual(dup.data["id"], first["id"])
        self.assertEqual(Report.objects.count(), 1)

    def test_duplicate_message_report_dedupes_per_message(self):
        msg = self._send("suspicious payment request", user=self.other).data
        first = self._report(self.other.id, message_id=msg["id"], expect=201)
        dup = self._report(self.other.id, message_id=msg["id"], expect=200)
        self.assertTrue(dup.data.get("duplicate"))
        self.assertEqual(dup.data["id"], first.data["id"])
        self.assertEqual(Report.objects.count(), 1)

    def test_new_report_allowed_after_resolution(self):
        first = self._report(self.other.id, category="spam").data
        Report.objects.filter(pk=first["id"]).update(status=Report.Status.DISMISSED)
        second = self._report(self.other.id, category="scam")
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(second.data["id"], first["id"])

    @override_settings(REST_FRAMEWORK=REST_FRAMEWORK_RATE)
    def test_report_endpoint_is_rate_limited(self):
        # 2/hour budget — two reports against *different* targets consume it,
        # and the third request is throttled (429). Different targets avoid
        # the duplicate guard (which would return 200 instead of creating).
        other2 = User.objects.create_user(
            username="msg_other2", email="msg_other2@example.com", password="test12345"
        )
        self._report(self.other.id, category="scam")
        self._report(other2.id, category="spam")
        res = self.client.post(
            "/api/v1/chat/reports/",
            {"target_user_id": self.other.id, "category": "other"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
