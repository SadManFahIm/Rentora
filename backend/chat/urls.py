from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BlockedUsersView,
    BlockUserView,
    ChatRoomViewSet,
    ChatSafetyEventsView,
    ChatUploadView,
    MessageViewSet,
    OnlineStatusView,
    ReportActionView,
    ReportCreateView,
    ReportListView,
    UnblockUserView,
)

router = DefaultRouter()
router.register("rooms", ChatRoomViewSet, basename="chatroom")

urlpatterns = [
    *router.urls,
    path(
        "rooms/<int:room_id>/messages/",
        MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="chatroom-messages",
    ),
    path("online-status/", OnlineStatusView.as_view(), name="chat-online-status"),
    path("upload/", ChatUploadView.as_view(), name="chat-upload"),
    path("safety/events/", ChatSafetyEventsView.as_view(), name="chat-safety-events"),
    # Report / block (Phase 12.4).
    path("reports/", ReportCreateView.as_view(), name="chat-report-create"),
    path("reports/admin/", ReportListView.as_view(), name="chat-report-list"),
    path("reports/<int:report_id>/action/", ReportActionView.as_view(), name="chat-report-action"),
    path("block/", BlockUserView.as_view(), name="chat-block"),
    path("blocked/", BlockedUsersView.as_view(), name="chat-blocked"),
    path("block/<int:user_id>/", UnblockUserView.as_view(), name="chat-unblock"),
]
