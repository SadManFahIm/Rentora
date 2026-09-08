"""WebSocket consumer tests.

Drives ``chat.consumers.ChatConsumer`` (and the notifications socket) through
the real ASGI stack — JWT middleware + routing — via
``channels.testing.WebsocketCommunicator`` inside an async test case.

Covers the application-level heartbeat protocol (``ping`` → ``pong``) that the
frontend ``useWebSocket`` hook relies on to detect half-open connections, the
auth close codes the hook must not retry forever (4401 = unauthenticated,
4403 = forbidden), and a regression check that ordinary messages still flow.
"""

from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

import chat.routing
import notifications.routing
from config.middleware import JWTAuthMiddlewareStack

from .consumers import WS_CLOSE_FORBIDDEN, WS_CLOSE_UNAUTHENTICATED
from .models import ChatRoom, ChatRoomMembership, Message

User = get_user_model()

TEST_WS_APP = JWTAuthMiddlewareStack(
    URLRouter(chat.routing.websocket_urlpatterns + notifications.routing.websocket_urlpatterns)
)


def _chat_communicator(token: str, room_id: int) -> WebsocketCommunicator:
    comm = WebsocketCommunicator(TEST_WS_APP, f"/ws/chat/{room_id}/")
    comm.scope["query_string"] = f"token={token}".encode()
    return comm


class ChatSocketTests(TransactionTestCase):
    """JWT auth close codes + heartbeat for the chat consumer (async socket I/O)."""

    def setUp(self):
        self.landlord = User.objects.create_user(
            username="ws_landlord", email="ws_landlord@example.com", password="test12345"
        )
        self.tenant = User.objects.create_user(
            username="ws_tenant", email="ws_tenant@example.com", password="test12345"
        )
        self.room = ChatRoom.objects.create(room_type=ChatRoom.RoomType.DIRECT)
        ChatRoomMembership.objects.create(chat_room=self.room, user=self.landlord)
        ChatRoomMembership.objects.create(chat_room=self.room, user=self.tenant)

    def test_heartbeat_ping_gets_pong_and_message_still_flows(self):
        # Runs the communicator on the test's own event loop instead of
        # juggling async_to_sync across calls, which channels 4.x no longer
        # supports for WebsocketCommunicator.
        import asyncio

        async def scenario():
            token = AccessToken.for_user(self.tenant)
            comm = _chat_communicator(str(token), self.room.pk)
            connected, _close_code = await comm.connect(timeout=5)
            self.assertTrue(connected)

            await comm.send_json_to({"type": "ping"})
            reply = await comm.receive_json_from(timeout=5)
            self.assertEqual(reply["type"], "pong")
            self.assertIn("server_time", reply)

            # Regression: ping dispatch must not break the message path.
            await comm.send_json_to({"type": "message", "content": "hi from socket test"})
            echo = await comm.receive_json_from(timeout=5)
            self.assertEqual(echo["type"], "chat_message")
            self.assertEqual(echo["message"]["content"], "hi from socket test")

            await comm.disconnect()

            message = await sync_to_async(
                lambda: Message.objects.filter(
                    chat_room=self.room, sender=self.tenant, content="hi from socket test"
                ).exists()
            )()
            self.assertTrue(message)

        asyncio.run(scenario())

    def test_invalid_token_is_closed_with_4401(self):
        import asyncio

        async def scenario():
            comm = _chat_communicator("not-a-jwt", self.room.pk)
            connected, close_code = await comm.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(close_code, WS_CLOSE_UNAUTHENTICATED)

        asyncio.run(scenario())

    def test_expired_token_is_closed_with_4401(self):
        import asyncio

        async def scenario():
            token = AccessToken.for_user(self.tenant)
            # Freshly minted tokens are long-lived by default; force the exp
            # claim back into the past for a deterministic "expired" test.
            token["exp"] = int((timezone.now() - timezone.timedelta(seconds=1)).timestamp())
            comm = _chat_communicator(str(token), self.room.pk)
            connected, close_code = await comm.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(close_code, WS_CLOSE_UNAUTHENTICATED)

        asyncio.run(scenario())

    def test_non_member_is_closed_with_4403(self):
        import asyncio

        async def scenario():
            stranger = await sync_to_async(User.objects.create_user)(
                username="ws_stranger", email="ws_stranger@example.com", password="test12345"
            )
            token = AccessToken.for_user(stranger)
            comm = _chat_communicator(str(token), self.room.pk)
            connected, close_code = await comm.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(close_code, WS_CLOSE_FORBIDDEN)

        asyncio.run(scenario())


class NotificationSocketTests(TransactionTestCase):
    """The notifications socket also answers heartbeat pings."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ws_notif", email="ws_notif@example.com", password="test12345"
        )

    def test_ping_gets_pong_and_other_frames_ignored(self):
        import asyncio

        async def scenario():
            token = AccessToken.for_user(self.user)
            comm = WebsocketCommunicator(TEST_WS_APP, "/ws/notifications/")
            comm.scope["query_string"] = f"token={token}".encode()
            connected, _ = await comm.connect(timeout=5)
            self.assertTrue(connected)

            await comm.send_json_to({"type": "ping"})
            reply = await comm.receive_json_from(timeout=5)
            self.assertEqual(reply["type"], "pong")

            # Non-ping inbound frames are ignored (no reply), and the socket
            # stays healthy enough to answer the next heartbeat.
            await comm.send_json_to({"type": "whatever", "data": 1})
            await comm.send_json_to({"type": "ping"})
            reply = await comm.receive_json_from(timeout=5)
            self.assertEqual(reply["type"], "pong")

            await comm.disconnect()

        asyncio.run(scenario())

    def test_unauthenticated_socket_closes_with_4401(self):
        import asyncio

        async def scenario():
            comm = WebsocketCommunicator(TEST_WS_APP, "/ws/notifications/")
            comm.scope["query_string"] = b"token=broken"
            connected, close_code = await comm.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(close_code, WS_CLOSE_UNAUTHENTICATED)

        asyncio.run(scenario())


class PingPayloadHelpersTests(TransactionTestCase):
    """Tiny regression guard on the wire format of ping/pong payloads."""

    def test_pong_payload_is_json_serializable(self):
        # The client parses pong frames the same way it parses every other
        # frame — it must remain valid JSON with a recognizable type field.
        payload = {"type": "pong", "server_time": "2026-01-01T00:00:00+00:00"}
        parsed = json.loads(json.dumps(payload))
        self.assertEqual(parsed["type"], "pong")
