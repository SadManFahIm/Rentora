"""E2E: the trust-flow chain through the real API (Tier 3 expansion).

Covers the report -> admin queue -> resolution -> block -> unblock path end
to end, exactly the way the browser drives it, plus the audit trail every
step must write. Tagged ``e2e`` so CI runs it in the dedicated E2E job
alongside the fraud/payments/KYC suites.
"""

from django.contrib.auth import get_user_model
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLogEntry
from chat.models import ChatRoom, ChatRoomMembership, Message, Report, UserBlock
from rooms.models import Room

User = get_user_model()


@tag("e2e")
class TrustFlowE2ETest(APITestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="trust_landlord",
            email="trust_landlord@example.com",
            password="test12345",
            role=User.Role.LANDLORD,
            nid_verified=True,
        )
        self.tenant = User.objects.create_user(
            username="trust_tenant",
            email="trust_tenant@example.com",
            password="test12345",
            role=User.Role.TENANT,
            tenant_verified=True,
        )
        self.admin = User.objects.create_user(
            username="trust_admin",
            email="trust_admin@example.com",
            password="test12345",
            is_staff=True,
        )
        self.room = Room.objects.create(
            owner=self.landlord,
            title="Trust Flow Studio",
            description="A room.",
            room_type="studio",
            price=12000,
            area="Uttara",
            address="Sector 4, Uttara",
            lat=23.8759,
            lng=90.3795,
            amenities=["wifi"],
            size_sqft=240,
        )
        # A direct chat room between landlord and tenant, with one message
        # that looks like a payment request (the report target).
        self.chat = ChatRoom.objects.create(room_type=ChatRoom.RoomType.DIRECT, listing=self.room)
        ChatRoomMembership.objects.create(chat_room=self.chat, user=self.landlord)
        ChatRoomMembership.objects.create(chat_room=self.chat, user=self.tenant)
        self.msg = Message.objects.create(
            chat_room=self.chat,
            sender=self.landlord,
            content="Send the advance to my bKash: 01711111111",
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _report(self, category="payment_fraud", description="Suspicious payment request"):
        return self.client.post(
            "/api/v1/chat/reports/",
            {
                "target_user_id": self.landlord.pk,
                "message_id": self.msg.pk,
                "category": category,
                "description": description,
            },
            format="json",
        )

    def test_full_trust_chain(self):
        # 1. Tenant reports the landlord's payment-request message.
        self._auth(self.tenant)
        res = self._report()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        report_id = res.data["id"]
        self.assertEqual(res.data["status"], Report.Status.OPEN)

        # 2. Duplicate report of the same target/message is collapsed (abuse
        #    guard) — the queue can't be stacked with repeats.
        res2 = self._report()
        self.assertEqual(res2.data["id"], report_id)

        # 3. The report lands in the admin queue.
        self._auth(self.admin)
        res = self.client.get("/api/v1/chat/reports/admin/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(r["id"] == report_id for r in res.data))

        # 4. A normal user cannot act on reports.
        self._auth(self.tenant)
        res = self.client.post(
            f"/api/v1/chat/reports/{report_id}/action/",
            {"action": "dismiss", "note": "nope"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Admin dismisses -> RESOLVED-state change and audit event.
        self._auth(self.admin)
        res = self.client.post(
            f"/api/v1/chat/reports/{report_id}/action/",
            {"action": "dismiss", "note": "No clear violation"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], Report.Status.DISMISSED)
        self.assertTrue(
            AuditLogEntry.objects.filter(action="report.dismiss", target_id=str(report_id)).exists()
        )

        # 6. Tenant blocks the landlord -> new chats between them are refused.
        self._auth(self.tenant)
        res = self.client.post("/api/v1/chat/block/", {"user_id": self.landlord.pk}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/v1/chat/blocked/")
        self.assertTrue(any(b["id"] == self.landlord.pk for b in res.data))
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.landlord.pk}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 7. Unblock restores the channel.
        res = self.client.delete(f"/api/v1/chat/block/{self.landlord.pk}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            UserBlock.objects.filter(blocker=self.tenant, blocked=self.landlord).exists()
        )
        res = self.client.post("/api/v1/chat/rooms/", {"user_id": self.landlord.pk}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 8. Every step is on the audit trail (admin view).
        self._auth(self.admin)
        res = self.client.get("/api/v1/audit/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        actions = [e["action"] for e in res.data]
        self.assertIn("report.created", actions)
        self.assertIn("report.dismiss", actions)
        self.assertIn("user.blocked", actions)
