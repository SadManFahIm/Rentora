"""API views for the fraud app.

Endpoints
---------
- ``GET /fraud/rooms/{room_id}/status/``  — public per-room fraud badge data
- ``GET /fraud/reports/``                 — list reports (owner: own rooms; admin: all)
- ``POST /fraud/rooms/{room_id}/scan/``   — re-scan a room (owner or admin)
- ``POST /fraud/reports/{report_id}/review/`` — admin: reviewed / dismissed
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from rooms.models import Room

from .models import FraudReport
from .serializers import (
    FraudReportSerializer,
    FraudReviewRequestSerializer,
    FraudStatusSerializer,
)
from .services.detectors import run_scan


class RoomFraudStatusView(APIView):
    """Public fraud status for one room — drives the 'under review' badge."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Fraud"],
        summary="Fraud status for a room",
        description="Public badge data. `flagged` is true whenever severity is not `clean`.",
        responses=FraudStatusSerializer,
    )
    def get(self, request, room_id):
        report = FraudReport.objects.filter(room_id=room_id).first()
        if report is None:
            return Response(
                {
                    "room_id": room_id,
                    "severity": FraudReport.Severity.CLEAN,
                    "score": 0,
                    "flagged": False,
                    "message": "No risk signals detected.",
                }
            )
        return Response(
            {
                "room_id": room_id,
                "severity": report.severity,
                "score": report.score,
                "flagged": report.is_flagged,
                "message": report.summary,
            }
        )


class FraudReportListView(APIView):
    """List fraud reports. Landlords see only their own rooms; admins see all.

    Filter with ``?status=open|reviewed|dismissed`` and ``?severity=high|...``.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="List fraud reports",
        description="Owners see reports for their own listings; admins see every report. "
        "Filter by `status` (open/reviewed/dismissed) or `severity`.",
        responses=FraudReportSerializer(many=True),
    )
    def get(self, request):
        if request.user.is_staff or request.user.role == "admin":
            queryset = FraudReport.objects.all()
        else:
            queryset = FraudReport.objects.filter(room__owner=request.user)

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        severity_filter = request.query_params.get("severity")
        if severity_filter:
            queryset = queryset.filter(severity=severity_filter)

        queryset = queryset.select_related("room__owner").prefetch_related(
            "signals", "room__images"
        )
        return Response(FraudReportSerializer(queryset, many=True, context={"request": request}).data)


class FraudRoomScanView(APIView):
    """Re-run the fraud detector on a room (owner of the room, or any admin)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Re-scan a room",
        description="Reruns every detector and replaces the room's report. "
        "Owner or admin only.",
        responses=FraudReportSerializer,
    )
    def post(self, request, room_id):
        room = get_object_or_404(Room, pk=room_id)
        if not (request.user.is_staff or room.owner_id == request.user.id):
            return Response(
                {"detail": "Only the listing owner or an admin can re-scan a room."},
                status=status.HTTP_403_FORBIDDEN,
            )
        report = run_scan(room)
        return Response(FraudReportSerializer(report, context={"request": request}).data)


class FraudReportReviewView(APIView):
    """Admin decision on an open report: mark reviewed or dismiss it.

    Admin here means Django staff *or* a user whose role is ``admin`` (the
    app-level flag) — the inline check keeps the two authorities consistent
    with how the frontend decides to show the review buttons.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Review or dismiss a fraud report",
        request=FraudReviewRequestSerializer,
        responses=FraudReportSerializer,
    )
    def post(self, request, report_id):
        if not (request.user.is_staff or request.user.role == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        report = get_object_or_404(FraudReport, pk=report_id)
        serializer = FraudReviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report.status = serializer.validated_data["action"]
        report.save(update_fields=["status", "updated_at"])
        return Response(FraudReportSerializer(report, context={"request": request}).data)
