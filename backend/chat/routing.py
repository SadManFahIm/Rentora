from django.urls import re_path

from . import consumers

# WebSocket URL patterns for the chat app.
# ws/chat/<room_id>/  →  ChatConsumer
websocket_urlpatterns = [
    re_path(r"^ws/chat/(?P<room_id>\d+)/$", consumers.ChatConsumer.as_asgi()),
]
