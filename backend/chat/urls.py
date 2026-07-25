from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChatRoomViewSet, MessageViewSet

router = DefaultRouter()
router.register("rooms", ChatRoomViewSet, basename="chatroom")

urlpatterns = router.urls + [
    path(
        "rooms/<int:room_id>/messages/",
        MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="chatroom-messages",
    ),
]
