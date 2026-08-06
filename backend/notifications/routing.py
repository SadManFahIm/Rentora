from django.urls import re_path

from . import consumers

# WebSocket URL patterns for the notifications app.
# ws/notifications/  →  NotificationConsumer
websocket_urlpatterns = [
    re_path(r"^ws/notifications/$", consumers.NotificationConsumer.as_asgi()),
]
