from django.urls import path

from .views import (
    FraudAuditLogView,
    FraudReportListView,
    FraudReportReviewView,
    FraudRingsView,
    FraudRoomScanView,
    FraudSummaryView,
    RoomFraudStatusView,
)

urlpatterns = [
    path("rooms/<int:room_id>/status/", RoomFraudStatusView.as_view(), name="fraud-room-status"),
    path("reports/", FraudReportListView.as_view(), name="fraud-reports"),
    path("summary/", FraudSummaryView.as_view(), name="fraud-summary"),
    path("audit/", FraudAuditLogView.as_view(), name="fraud-audit"),
    path("rings/", FraudRingsView.as_view(), name="fraud-rings"),
    path("rooms/<int:room_id>/scan/", FraudRoomScanView.as_view(), name="fraud-room-scan"),
    path(
        "reports/<int:report_id>/review/",
        FraudReportReviewView.as_view(),
        name="fraud-report-review",
    ),
]
