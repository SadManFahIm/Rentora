from django.urls import path

from .views import (
    FraudReportListView,
    FraudReportReviewView,
    FraudRoomScanView,
    RoomFraudStatusView,
)

urlpatterns = [
    path("rooms/<int:room_id>/status/", RoomFraudStatusView.as_view(), name="fraud-room-status"),
    path("reports/", FraudReportListView.as_view(), name="fraud-reports"),
    path("rooms/<int:room_id>/scan/", FraudRoomScanView.as_view(), name="fraud-room-scan"),
    path(
        "reports/<int:report_id>/review/",
        FraudReportReviewView.as_view(),
        name="fraud-report-review",
    ),
]
