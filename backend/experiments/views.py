"""Experiment API — assignment, exposure and conversion tracking.

    GET  /api/v1/experiments/active/   active experiments + caller's variant
    POST /api/v1/experiments/exposure/    {experiment_key, variant_key, ...}
    POST /api/v1/experiments/conversion/  {experiment_key, variant_key, event_name, ...}

Exposure is explicitly client-triggered (a user *saw* a variant); conversion
events are stored in the analytics event store with experiment context.
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttling import TrustedScopedRateThrottle

from .services import active_experiments, record_conversion, record_exposure


class ExposureSerializer(serializers.Serializer):
    experiment_key = serializers.CharField(max_length=128)
    variant_key = serializers.CharField(max_length=64)
    anonymous_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    context = serializers.JSONField(required=False)


class ConversionSerializer(ExposureSerializer):
    event_name = serializers.CharField(max_length=64)


class ActiveExperimentsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TrustedScopedRateThrottle]
    throttle_scope = "experiments"

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        anon = request.query_params.get("anonymous_id")
        return Response(
            {"experiments": active_experiments(user=user, request=request, anonymous_id=anon)}
        )


class ExposureView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TrustedScopedRateThrottle]
    throttle_scope = "experiments"

    def post(self, request):
        serializer = ExposureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        ok = record_exposure(
            data["experiment_key"],
            data["variant_key"],
            user=user,
            anonymous_id=data.get("anonymous_id") or None,
            request=request,
            context=data.get("context"),
        )
        return Response({"recorded": ok}, status=status.HTTP_200_OK)


class ConversionView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [TrustedScopedRateThrottle]
    throttle_scope = "experiments"

    def post(self, request):
        serializer = ConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user if request.user.is_authenticated else None
        ok = record_conversion(
            data["experiment_key"],
            data["variant_key"],
            data["event_name"],
            user=user,
            anonymous_id=data.get("anonymous_id") or None,
            request=request,
            context=data.get("context"),
        )
        return Response({"recorded": ok}, status=status.HTTP_200_OK)
