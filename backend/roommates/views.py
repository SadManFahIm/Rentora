"""API views for the roommates app.

Endpoints
---------
- ``GET/PUT /roommates/profile/``        — the caller's own profile (create/update)
- ``GET /roommates/matches/``            — scored match suggestions
- ``GET/POST /roommates/requests/``      — list my requests / send one
- ``POST /roommates/requests/{id}/action/`` — approve or reject an incoming request
"""

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.utils import create_notification

from .models import RoommateMatchRequest, RoommateProfile
from .serializers import (
    RoommateMatchSerializer,
    RoommateProfileSerializer,
    RoommateRequestActionSerializer,
    RoommateRequestCreateSerializer,
    RoommateRequestSerializer,
)
from .services.matching import find_matches


class RoommateProfileView(APIView):
    """Read or upsert the caller's own roommate profile."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Roommates"],
        summary="Get my roommate profile",
        description="Returns 404 if the caller hasn't created a profile yet.",
        responses=RoommateProfileSerializer,
    )
    def get(self, request):
        profile = RoommateProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response({"detail": "No roommate profile yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(RoommateProfileSerializer(profile).data)

    @extend_schema(
        tags=["Roommates"],
        summary="Create or update my roommate profile",
        description="Upsert: creates the profile on first call, updates it afterwards.",
        request=RoommateProfileSerializer,
        responses=RoommateProfileSerializer,
    )
    def put(self, request):
        profile, _created = RoommateProfile.objects.get_or_create(user=request.user)
        serializer = RoommateProfileSerializer(profile, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class RoommateMatchesView(APIView):
    """Ranked roommate suggestions for the caller.

    Requires a profile (that's the thing being matched). Candidates exclude
    the caller and anyone they've already sent a request to.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Roommates"],
        summary="Get roommate match suggestions",
        description="Best-first ranked candidates with a 0-100 match score and reasons. "
        "Requires the caller to have a roommate profile.",
        responses=RoommateMatchSerializer(many=True),
    )
    def get(self, request):
        profile = RoommateProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response(
                {"detail": "Create a roommate profile first to see matches."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        already_requested = set(
            RoommateMatchRequest.objects.filter(sender=request.user).values_list("receiver_id", flat=True)
        )
        results = find_matches(profile, exclude_users=already_requested)
        data = RoommateMatchSerializer(
            [
                {"score": m.score, "reasons": m.reasons, "profile": m.profile}
                for m in results
            ],
            many=True,
            context={"request": request},
        ).data
        return Response(data)


class RoommateRequestListCreateView(APIView):
    """List the caller's requests (both directions) or send a new one."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Roommates"],
        summary="List my roommate requests",
        description="All requests where the caller is sender or receiver, newest first. "
        "Each item carries a `direction` field (incoming/outgoing).",
        responses=RoommateRequestSerializer(many=True),
    )
    def get(self, request):
        # Q-object OR instead of queryset .union(): SQLite rejects ORDER BY on
        # compound statements, and an OR is a plain single query either way.
        requests = RoommateMatchRequest.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        ).order_by("-created_at")
        return Response(RoommateRequestSerializer(requests, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["Roommates"],
        summary="Send a roommate request",
        description="Request a roommate match with another user. Duplicate requests "
        "between the same pair are rejected (unique sender/receiver).",
        request=RoommateRequestCreateSerializer,
        responses=RoommateRequestSerializer,
    )
    def post(self, request):
        serializer = RoommateRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receiver_id = serializer.validated_data["receiver_id"]

        if receiver_id == request.user.id:
            raise ValidationError({"receiver_id": "You cannot send a roommate request to yourself."})
        if not RoommateProfile.objects.filter(user_id=receiver_id, is_looking=True).exists():
            raise ValidationError({"receiver_id": "This user has no active roommate profile."})

        try:
            roommate_request = RoommateMatchRequest.objects.create(
                sender=request.user,
                receiver_id=receiver_id,
                message=serializer.validated_data.get("message", ""),
            )
        except IntegrityError:
            raise ValidationError(
                {"receiver_id": "A roommate request between you and this user already exists."}
            )

        create_notification(
            user=roommate_request.receiver,
            notification_type="roommate_request",
            title="New roommate request",
            message=f"{request.user.get_full_name() or request.user.username} wants to share a room with you.",
            action_url="/roommates",
        )
        return Response(
            RoommateRequestSerializer(roommate_request, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class RoommateRequestActionView(APIView):
    """Approve or reject an incoming roommate request."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Roommates"],
        summary="Approve or reject a roommate request",
        request=RoommateRequestActionSerializer,
        responses=RoommateRequestSerializer,
    )
    def post(self, request, request_id):
        roommate_request = get_object_or_404(
            RoommateMatchRequest, pk=request_id, receiver=request.user, status="pending"
        )
        serializer = RoommateRequestActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        roommate_request.status = (
            RoommateMatchRequest.Status.APPROVED
            if serializer.validated_data["action"] == "approve"
            else RoommateMatchRequest.Status.REJECTED
        )
        roommate_request.save(update_fields=["status", "updated_at"])

        if roommate_request.status == RoommateMatchRequest.Status.APPROVED:
            create_notification(
                user=roommate_request.sender,
                notification_type="roommate_approved",
                title="Roommate request approved 🎉",
                message=f"{roommate_request.receiver.get_full_name() or roommate_request.receiver.username} accepted your roommate request.",
                action_url="/roommates",
            )
            # Turn off both profiles' "looking" flag so neither keeps
            # receiving suggestions once they've paired up.
            RoommateProfile.objects.filter(user=roommate_request.sender).update(is_looking=False)
            RoommateProfile.objects.filter(user=roommate_request.receiver).update(is_looking=False)

        return Response(RoommateRequestSerializer(roommate_request, context={"request": request}).data)
