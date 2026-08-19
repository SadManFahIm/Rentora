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


class FraudAuditLogView(APIView):
    """Admin-only view of the append-only fraud audit trail.

    Reads the same ``AuditLogEntry`` rows the review/scan actions write — no
    separate log store. Only ``fraud.*`` actions are returned.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Fraud audit trail",
        description="Admin-only append-only audit log of fraud review/scan actions.",
    )
    def get(self, request):
        if not (request.user.is_staff or request.user.role == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from audit.models import AuditLogEntry

        entries = AuditLogEntry.objects.filter(action__startswith="fraud.").select_related("actor")[
            :100
        ]
        return Response(
            [
                {
                    "id": e.id,
                    "action": e.action,
                    "actor": e.actor.username if e.actor else None,
                    "room_id": (e.detail or {}).get("room_id"),
                    "target_id": e.target_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ]
        )


class FraudRingsView(APIView):
    """Admin-only coordinated-account rings — the Trust & Safety desk view.

    Computed live from real platform data (shared phones, shared audit IPs +
    same-area listings). A ring is a review queue, never an automatic block.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Fraud rings",
        description="Admin-only connected groups of coordinated accounts with evidence.",
    )
    def get(self, request):
        if not (request.user.is_staff or request.user.role == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from .services.rings import detect_rings

        return Response(detect_rings())


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

    Filters (all optional): ``status`` (open/reviewed/dismissed), ``severity``
    (clean/low/medium/high), ``area`` (case-insensitive listing area match),
    ``detector`` (signal detector key), ``q`` (title/owner search) and
    ``ordering`` (``-score`` default, or ``score`` / ``-created_at`` /
    ``created_at`` / ``-price``).
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="List fraud reports",
        description="Owners see reports for their own listings; admins see every report. "
        "Filter by status/severity/area/detector/text and sort by score/date/price.",
        responses=FraudReportSerializer(many=True),
    )
    def get(self, request):
        from django.db.models import Q

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

        area_filter = request.query_params.get("area")
        if area_filter:
            queryset = queryset.filter(room__area__iexact=area_filter)

        detector_filter = request.query_params.get("detector")
        if detector_filter:
            queryset = queryset.filter(signals__detector=detector_filter).distinct()

        text_filter = (request.query_params.get("q") or "").strip()
        if text_filter:
            queryset = queryset.filter(
                Q(room__title__icontains=text_filter)
                | Q(room__owner__username__icontains=text_filter)
                | Q(room__owner__email__icontains=text_filter)
            )

        ordering = request.query_params.get("ordering", "-score")
        allowed = {
            "-score": "-score",
            "score": "score",
            "-created_at": "-created_at",
            "created_at": "created_at",
            "-price": "-room__price",
            "price": "room__price",
        }
        queryset = queryset.order_by(allowed.get(ordering, "-score"))

        queryset = queryset.select_related("room__owner").prefetch_related(
            "signals", "room__images"
        )
        return Response(
            FraudReportSerializer(queryset, many=True, context={"request": request}).data
        )


class FraudSummaryView(APIView):
    """Admin-only aggregate stats for the fraud operations dashboard.

    Counts are computed from the existing fraud engine's persisted reports —
    no second detection pass, just aggregation of what the detectors already
    wrote.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Fraud dashboard summary",
        description="Admin-only totals: flagged/high/critical/open/reviewed/dismissed/clean "
        "plus counts per severity and per detector.",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                    "flagged": {"type": "integer"},
                    "high_risk": {"type": "integer"},
                    "medium_risk": {"type": "integer"},
                    "low_risk": {"type": "integer"},
                    "open": {"type": "integer"},
                    "reviewed": {"type": "integer"},
                    "dismissed": {"type": "integer"},
                    "clean": {"type": "integer"},
                    "by_detector": {"type": "object", "additionalProperties": {"type": "integer"}},
                },
            }
        },
    )
    def get(self, request):
        from django.db.models import Count

        if not (request.user.is_staff or request.user.role == "admin"):
            return Response(
                {"detail": "Admin access required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from django.db.models import Q

        from .models import FraudSignal

        agg = FraudReport.objects.aggregate(
            total=Count("id"),
            flagged=Count("id", filter=Q(severity__in=["low", "medium", "high"])),
            high_risk=Count("id", filter=Q(severity="high")),
            medium_risk=Count("id", filter=Q(severity="medium")),
            low_risk=Count("id", filter=Q(severity="low")),
            open=Count("id", filter=Q(status="open")),
            reviewed=Count("id", filter=Q(status="reviewed")),
            dismissed=Count("id", filter=Q(status="dismissed")),
            clean=Count("id", filter=Q(severity="clean")),
        )
        by_detector = dict(FraudSignal.objects.values_list("detector").annotate(c=Count("id")))
        return Response({**agg, "by_detector": by_detector})


class FraudRoomScanView(APIView):
    """Re-run the fraud detector on a room (owner of the room, or any admin)."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Fraud"],
        summary="Re-scan a room",
        description="Reruns every detector and replaces the room's report. Owner or admin only.",
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
        # Audit trail: who resolved/dismissed a report and from where.
        from audit.services import log_action

        log_action(
            actor=request.user,
            action=f"fraud.report.{serializer.validated_data['action']}",
            target=report,
            request=request,
            detail={"room_id": report.room_id},
        )
        return Response(FraudReportSerializer(report, context={"request": request}).data)
