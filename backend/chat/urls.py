from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChatRoomViewSet, ChatUploadView, MessageViewSet, OnlineStatusView

router = DefaultRouter()
router.register("rooms", ChatRoomViewSet, basename="chatroom")

urlpatterns = router.urls + [
    path(
        "rooms/<int:room_id>/messages/",
        MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="chatroom-messages",
    ),
    path("online-status/", OnlineStatusView.as_view(), name="chat-online-status"),
    path("upload/", ChatUploadView.as_view(), name="chat-upload"),
]
