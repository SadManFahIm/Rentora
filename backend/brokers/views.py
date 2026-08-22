"""Broker network endpoints."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import log_action
from monetization.models import Commission, Payout
from monetization.serializers import CommissionSerializer, PayoutSerializer
from monetization.services.payouts import PayoutError, available_balance, request_payout
from notifications.models import Notification
from notifications.utils import create_notification

from .models import BrokerProfile, BrokerVerification
from .serializers import BrokerProfileSerializer, BrokerVerificationSerializer
from .services import get_or_create_profile, screen_broker


def _is_admin(user) -> bool:
    return user.is_staff or user.role == user.Role.ADMIN


class BrokerRegisterView(APIView):
    """Submit a broker profile + first verification (PENDING)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(settings, "BROKER_NETWORK_ENABLED", True):
            return Response(
                {"detail": "The broker network is not enabled."}, status=status.HTTP_403_FORBIDDEN
            )

        profile = get_or_create_profile(request.user)
        if profile.status in (
            BrokerProfile.Status.PENDING,
            BrokerProfile.Status.VERIFIED,
        ):
            return Response(
                {"detail": f"You already have a {profile.status} broker profile."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.license_number = request.data.get("license_number", profile.license_number)
        profile.years_experience = request.data.get("years_experience", profile.years_experience)
        profile.specialization = request.data.get("specialization", profile.specialization)
        profile.areas = request.data.get("areas", profile.areas)
        profile.status = BrokerProfile.Status.PENDING
        profile.save()

        verification = BrokerVerification.objects.create(
            profile=profile,
            documents=request.data.get("documents", []),
            notes=request.data.get("notes", ""),
        )
        screen = screen_broker(verification)
        verification.auto_screen_score = screen["score"]
        verification.auto_screen_result = screen["result"]
        verification.auto_screen_detail = screen
        verification.save(
            update_fields=["auto_screen_score", "auto_screen_result", "auto_screen_detail"]
        )

        if request.user.role == request.user.Role.TENANT:
            request.user.role = request.user.Role.BROKER
            request.user.save(update_fields=["role"])

        create_notification(
            user=request.user,
            notification_type=Notification.Type.BROKER_SUBMITTED,
            title="Broker verification submitted",
            message="Your broker profile is under review. We'll notify you once it's verified.",
            action_url="/dashboard?tab=broker",
        )
        log_action(
            actor=request.user,
            action="broker.submitted",
            target=profile,
            detail={"screen": screen["result"], "score": screen["score"]},
        )

        return Response(
            {
                "profile": BrokerProfileSerializer(profile).data,
                "verification": BrokerVerificationSerializer(verification).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BrokerProfileView(APIView):
    """Read/update the caller's broker profile (admins may target a pk)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_or_create_profile(request.user)
        return Response(BrokerProfileSerializer(profile).data)

    def put(self, request):
        profile = get_or_create_profile(request.user)
        for field in ("license_number", "years_experience", "specialization", "areas"):
            if field in request.data:
                setattr(profile, field, request.data[field])
        profile.save()
        log_action(actor=request.user, action="broker.profile_updated", target=profile)
        return Response(BrokerProfileSerializer(profile).data)


class BrokerReviewView(APIView):
    """Admin approves/rejects a broker verification."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        profile_id = request.data.get("profile_id")
        decision = request.data.get("decision")
        note = request.data.get("note", "")

        if decision not in ("approve", "reject"):
            return Response(
                {"detail": "decision must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            profile = BrokerProfile.objects.select_related("user").get(pk=profile_id)
        except (BrokerProfile.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            verification = (
                BrokerVerification.objects.filter(profile=profile).order_by("-created_at").first()
            )
            new_status = (
                BrokerProfile.Status.VERIFIED
                if decision == "approve"
                else BrokerProfile.Status.REJECTED
            )
            profile.status = new_status
            profile.save(update_fields=["status", "updated_at"])
            if verification is not None:
                verification.status = (
                    BrokerVerification.Status.VERIFIED
                    if decision == "approve"
                    else BrokerVerification.Status.REJECTED
                )
                verification.notes = note
                verification.reviewed_at = timezone.now()
                verification.reviewed_by = request.user
                verification.save(
                    update_fields=["status", "notes", "reviewed_at", "reviewed_by", "updated_at"]
                )

        if decision == "approve":
            create_notification(
                user=profile.user,
                notification_type=Notification.Type.BROKER_VERIFIED,
                title="Broker profile verified",
                message="Congratulations! Your broker profile is verified. Share your referral "
                "code to start earning commissions.",
                action_url="/dashboard?tab=broker",
            )
        else:
            create_notification(
                user=profile.user,
                notification_type=Notification.Type.BROKER_REJECTED,
                title="Broker profile rejected",
                message="Your broker verification was rejected. Review the note and resubmit.",
                action_url="/dashboard?tab=broker",
            )
        log_action(
            actor=request.user,
            action=f"broker.{decision}",
            target=profile,
            detail={"note": note},
        )
        return Response(BrokerProfileSerializer(profile).data)


class BrokerDashboardView(APIView):
    """Broker overview: profile, balance, commission summary, referral link."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_or_create_profile(request.user)
        commissions = Commission.objects.filter(recipient=request.user)
        pending = commissions.filter(status=Commission.Status.PENDING)
        paid = commissions.filter(status=Commission.Status.PAID)

        from django.db.models import Sum

        return Response(
            {
                "profile": BrokerProfileSerializer(profile).data,
                "available_balance": available_balance(request.user),
                "summary": {
                    "pending_count": pending.count(),
                    "pending_total": pending.aggregate(total=Sum("amount"))["total"] or 0,
                    "paid_total": paid.aggregate(total=Sum("amount"))["total"] or 0,
                },
                "recent_commissions": CommissionSerializer(commissions[:5], many=True).data,
                "share_url": f"/rooms?ref={profile.referral_code}",
            }
        )


class BrokerCommissionsView(APIView):
    """List the caller's commissions (optional status filter)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = Commission.objects.filter(recipient=request.user)
        commission_status = request.query_params.get("status")
        if commission_status in Commission.Status.values:
            queryset = queryset.filter(status=commission_status)
        return Response(CommissionSerializer(queryset, many=True).data)


class BrokerPayoutsView(APIView):
    """List the caller's payout requests."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        payouts = Payout.objects.filter(recipient=request.user)
        return Response(PayoutSerializer(payouts, many=True).data)


class BrokerPayoutRequestView(APIView):
    """Request a payout of earned commissions."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        method = request.data.get("method", "bkash")
        if method not in Payout.Method.values:
            return Response(
                {"detail": f"method must be one of {Payout.Method.values}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payout = request_payout(
                user=request.user,
                amount=request.data.get("amount"),
                method=method,
                account_details=request.data.get("account_details", {}),
            )
        except PayoutError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayoutSerializer(payout).data, status=status.HTTP_201_CREATED)
