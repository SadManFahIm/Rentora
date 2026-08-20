"""Admin revenue surface: dashboard totals, payout queue decisions."""

from __future__ import annotations

from django.db.models import Count, Sum
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Commission, Payout, RevenueLedgerEntry
from .serializers import (
    CommissionSerializer,
    PayoutSerializer,
    RevenueLedgerEntrySerializer,
)
from .services import payouts as payout_service
from .services.ledger import REVENUE_ENTRY_TYPES
from .services.payouts import PayoutError


def _is_admin(user) -> bool:
    return user.is_staff or user.role == user.Role.ADMIN


class RevenueDashboardView(APIView):
    """Aggregated platform revenue + obligations + pending payout queue."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)

        revenue = RevenueLedgerEntry.objects.filter(entry_type__in=REVENUE_ENTRY_TYPES)
        by_scope = list(
            revenue.values("scope").annotate(
                gross=Sum("gross_amount"), platform=Sum("platform_amount")
            )
        )
        totals = revenue.aggregate(gross=Sum("gross_amount"), platform=Sum("platform_amount"))

        # Monthly recurring revenue: sum of active subscriptions' plan price.
        from subscriptions.models import Subscription

        mrr = (
            Subscription.objects.filter(status=Subscription.Status.ACTIVE)
            .select_related("plan")
            .aggregate(total=Sum("plan__price"))["total"]
            or 0
        )

        pending = Payout.objects.filter(status=Payout.Status.PENDING)
        pending_summary = pending.aggregate(count=Count("id"), total=Sum("amount"))
        partner_obligations = (
            Commission.objects.filter(status=Commission.Status.PENDING).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        return Response(
            {
                "revenue_by_scope": by_scope,
                "total_revenue": totals["gross"],
                "platform_revenue": totals["platform"],
                "mrr": mrr,
                "partner_obligations": partner_obligations,
                "pending_payouts": {
                    "count": pending_summary["count"],
                    "total": pending_summary["total"],
                },
                "recent_ledger": RevenueLedgerEntrySerializer(revenue[:15], many=True).data,
                "recent_commissions": CommissionSerializer(
                    Commission.objects.select_related("recipient")[:10], many=True
                ).data,
                "recent_payouts": PayoutSerializer(
                    Payout.objects.select_related("recipient")[:10], many=True
                ).data,
            }
        )


class PayoutAdminListView(APIView):
    """Admin list of payout requests, optionally filtered by status."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        queryset = Payout.objects.select_related("recipient")
        payout_status = request.query_params.get("status")
        if payout_status in Payout.Status.values:
            queryset = queryset.filter(status=payout_status)
        return Response(PayoutSerializer(queryset, many=True).data)


class PayoutDecisionView(APIView):
    """Admin approve/reject of a payout request."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            payout = Payout.objects.get(pk=pk)
        except Payout.DoesNotExist:
            return Response({"detail": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get("action")
        reason = request.data.get("reason", "")
        try:
            if action == "approve":
                payout_service.approve_payout(payout, request.user)
            elif action == "reject":
                payout_service.reject_payout(payout, request.user, reason)
            else:
                return Response(
                    {"detail": "action must be 'approve' or 'reject'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except PayoutError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayoutSerializer(payout).data)


class PayoutMarkPaidView(APIView):
    """Admin marks an approved payout as sent."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            payout = Payout.objects.get(pk=pk)
        except Payout.DoesNotExist:
            return Response({"detail": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            payout_service.mark_paid(payout, request.user, request.data.get("reference", ""))
        except PayoutError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayoutSerializer(payout).data)
