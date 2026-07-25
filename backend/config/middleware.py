"""ASGI middleware that authenticates WebSocket connections via a JWT.

Clients connect with the access token in the query string::

    ws://localhost:8000/ws/chat/<room_id>/?token=<jwt>

The token is validated with SimpleJWT; on success the matching user is placed
on ``scope["user"]``, otherwise ``AnonymousUser`` is used and the consumer is
responsible for rejecting the connection.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


@database_sync_to_async
def _get_user(user_id: int):
    """Fetch an active user by id, or AnonymousUser if not found/inactive."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()
    return user if user.is_active else AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Populate ``scope["user"]`` from a ``?token=`` query-string JWT."""

    async def __call__(self, scope, receive, send):
        token = self._extract_token(scope)
        scope["user"] = await self._authenticate(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token_list = params.get("token")
        return token_list[0] if token_list else None

    @staticmethod
    async def _authenticate(raw_token: str):
        try:
            access = AccessToken(raw_token)
        except (InvalidToken, TokenError):
            return AnonymousUser()
        user_id = access.get("user_id")
        if user_id is None:
            return AnonymousUser()
        return await _get_user(user_id)


def JWTAuthMiddlewareStack(inner):
    """Convenience wrapper mirroring channels' ``AuthMiddlewareStack``."""
    return JWTAuthMiddleware(inner)
