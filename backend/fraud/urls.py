from django.urls import path

from .views import (
    FraudAuditLogView,
    FraudGraphAnomaliesView,
    FraudGraphEdgeListView,
    FraudGraphNodeListView,
    FraudGraphNodeNeighborsView,
    FraudGraphOverviewView,
    FraudReportListView,
    FraudReportReviewView,
    FraudRingsView,
    FraudRoomScanView,
    FraudSummaryView,
    PhotoGeoMismatchesView,
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
    # Stage 3 — Persistent Fraud Graph
    path("graph/", FraudGraphOverviewView.as_view(), name="fraud-graph-overview"),
    path("graph/nodes/", FraudGraphNodeListView.as_view(), name="fraud-graph-nodes"),
    path("graph/edges/", FraudGraphEdgeListView.as_view(), name="fraud-graph-edges"),
    path(
        "graph/nodes/<int:node_id>/neighbors/",
        FraudGraphNodeNeighborsView.as_view(),
        name="fraud-graph-node-neighbors",
    ),
    path("graph/anomalies/", FraudGraphAnomaliesView.as_view(), name="fraud-graph-anomalies"),
    # Stage 5 — Photo-Geo Authenticity
    path(
        "photo-geo/mismatches/", PhotoGeoMismatchesView.as_view(), name="fraud-photo-geo-mismatches"
    ),
]
