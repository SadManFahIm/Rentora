"""
ASGI config for config project.

Exposes the ASGI callable as a module-level variable named ``application``.
Routes HTTP to Django and WebSocket to Channels (JWT-authenticated).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Initialise Django (populates the app registry) BEFORE importing anything that
# touches models — the routing/consumer imports below rely on this.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

import chat.routing  # noqa: E402
from config.middleware import JWTAuthMiddlewareStack  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(chat.routing.websocket_urlpatterns)
        ),
    }
)
