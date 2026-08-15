"""Phase 12.4 — Report / block tests.

Covers the spec's report/block matrix:

- reporting: user reports, message reports (suspicious payment request),
  category validation, self-report guard, message-must-belong-to-target
- admin moderation queue: auth, filtering
- admin actions: dismiss / warn / suspend / escalate, each with an audit
  entry and the right notifications
- block/unblock: idempotent block, self-block guard, list, unblock,
  and *enforcement* — a blocked pair can't message (REST) or open a new
  direct chat, and messaging works again after unblock
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from notifications.models import Notification

from .models import ChatRoom, Report, UserBlock

User = get_user_model()


class ReportBlockBase(APITestCase):
    def setUp(self):
        # The report endpoint is throttled (Tier-1 quick win). Tests create
        # fresh users per test but SQLite rolls the pk sequence back, so the
        # throttle bucket (keyed by user id) would leak across tests — clear
        # it like copilot/tests.py does.
        cache.clear()
        self.reporter = User.objects.create_user(
            username="report_reporter", email="reporter@example.com", password="test12345"
        )
        self.target = User.objects.create_user(
            username="report_target", email="target@example.com", password="test12345"
        )
        self.admin = User.objects.create_superuser(
            username="report_admin", email="radmin@example.com", password="test12345"
        )
        self.client.force_authenticate(user=self.reporter)
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.target.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.room = ChatRoom.objects.get(pk=res.data["id"])

    def _send(self, content, user=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.post(
            f"/api/v1/chat/rooms/{self.room.id}/messages/",
            {"content": content},
            format="json",
        )
        return res

    def _report(self, target_id, category="scam", message_id=None, description="", expect=201):
        self.client.force_authenticate(user=self.reporter)
        payload = {"target_user_id": target_id, "category": category}
        if message_id is not None:
            payload["message_id"] = message_id
        if description:
            payload["description"] = description
        res = self.client.post("/api/v1/chat/reports/", payload, format="json")
        self.assertEqual(res.status_code, expect, res.data)
        return res


class ReportCreationTests(ReportBlockBase):
    def test_unauthenticated_report_is_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(
            "/api/v1/chat/reports/", {"target_user_id": self.target.id}, format="json"
        )
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_report_user_lands_in_queue(self):
        res = self._report(self.target.id, category="harassment", description="Keeps messaging me")
        self.assertEqual(res.data["target_username"], self.target.username)
        self.assertEqual(res.data["category"], "harassment")
        self.assertEqual(res.data["status"], "open")
        report = Report.objects.get()
        self.assertEqual(report.reporter, self.reporter)
        self.assertEqual(report.target_user, self.target)

    def test_report_specific_message_suspicious_payment(self):
        # The reported message must come from the reported user.
        msg = self._send("send the deposit to my bkash 01712345678", user=self.target).data
        res = self._report(
            self.target.id,
            category="payment_fraud",
            message_id=msg["id"],
            description="Suspicious payment request",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["message"], msg["id"])

    def test_cannot_report_yourself(self):
        self._report(self.reporter.id, expect=400)

    def test_message_must_belong_to_reported_user(self):
        # A message sent by the reporter cannot be attached to a report of the
        # other user.
        msg = self._send("hello there").data
        self._report(self.target.id, message_id=msg["id"], expect=400)

    def test_invalid_category_rejected(self):
        self._report(self.target.id, category="not_a_category", expect=400)


class ReportModerationTests(ReportBlockBase):
    def test_queue_is_admin_only(self):
        self._report(self.target.id)
        self.client.force_authenticate(user=self.reporter)
        res = self.client.get("/api/v1/chat/reports/admin/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/chat/reports/admin/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["category"], "scam")

    def _act(self, report_id, action, note="", user=None, expect=200):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.post(
            f"/api/v1/chat/reports/{report_id}/action/",
            {"action": action, "note": note},
            format="json",
        )
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def test_dismiss_resolves_report_and_audits(self):
        report = self._report(self.target.id).data
        self.client.force_authenticate(user=self.admin)
        self._act(report["id"], "dismiss", note="No evidence of a scam.")
        report_db = Report.objects.get(pk=report["id"])
        self.assertEqual(report_db.status, Report.Status.DISMISSED)
        self.assertEqual(report_db.action_taken, Report.Action.DISMISS)
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="report.dismiss").exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.reporter, notification_type=Notification.Type.REPORT_RESOLVED
            ).exists()
        )

    def test_warn_notifies_the_reported_user(self):
        report = self._report(self.target.id).data
        self.client.force_authenticate(user=self.admin)
        self._act(report["id"], "warn", note="Stop requesting off-platform payments.")
        self.assertEqual(Report.objects.get(pk=report["id"]).status, Report.Status.RESOLVED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.target, notification_type=Notification.Type.ACCOUNT_WARNING
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="report.warn").exists()
        )

    def test_suspend_deactivates_the_user(self):
        report = self._report(self.target.id).data
        self.client.force_authenticate(user=self.admin)
        self._act(report["id"], "suspend", note="Repeat payment-fraud reports.")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(
            Notification.objects.filter(
                user=self.target, notification_type=Notification.Type.ACCOUNT_SUSPENDED
            ).exists()
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="report.suspend").exists()
        )

    def test_escalate_marks_escalated(self):
        report = self._report(self.target.id).data
        self.client.force_authenticate(user=self.admin)
        self._act(report["id"], "escalate", note="Needs a human dispute review.")
        self.assertEqual(Report.objects.get(pk=report["id"]).status, Report.Status.ESCALATED)
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.admin, action="report.escalate").exists()
        )

    def test_non_admin_cannot_act(self):
        report = self._report(self.target.id).data
        self.client.force_authenticate(user=self.reporter)
        self._act(report["id"], "dismiss", expect=403)


class BlockTests(ReportBlockBase):
    def _block(self, target_id, user=None, expect=200):
        if user is not None:
            self.client.force_authenticate(user=user)
        res = self.client.post("/api/v1/chat/block/", {"user_id": target_id}, format="json")
        self.assertEqual(res.status_code, expect, res.data)
        return res

    def test_block_is_idempotent(self):
        self._block(self.target.id)
        self._block(self.target.id)
        self.assertEqual(UserBlock.objects.count(), 1)

    def test_cannot_block_yourself(self):
        self._block(self.reporter.id, expect=400)

    def test_blocked_list_returns_blocked_users(self):
        self._block(self.target.id)
        res = self.client.get("/api/v1/chat/blocked/")
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["id"], self.target.id)

    def test_blocked_pair_cannot_message_in_existing_room(self):
        self._block(self.target.id)
        # The blocker can't message...
        res = self._send("hello", user=self.reporter)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # ...and the blocked user can't either (blocking is mutual).
        res = self._send("hello", user=self.target)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_blocked_user_cannot_start_new_direct_chat(self):
        stranger = User.objects.create_user(
            username="blocked_stranger", email="blocked_stranger@example.com", password="x"
        )
        self.client.force_authenticate(user=stranger)
        self._block(self.target.id)  # stranger blocks the target
        self.client.force_authenticate(user=self.target)
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": stranger.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unblock_restores_messaging(self):
        self._block(self.target.id)
        res = self.client.delete(f"/api/v1/chat/block/{self.target.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        res = self._send("hello again", user=self.reporter)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_unblock_unknown_user_is_404(self):
        res = self.client.delete(f"/api/v1/chat/block/{self.target.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
