"""Marketplace endpoints: provider onboarding, services CRUD, orders,
confirmation, and cross-sell recommendations."""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification

from .models import AddonOrder, AddonProvider, AddonService
from .serializers import (
    AddonOrderSerializer,
    AddonProviderSerializer,
    AddonServiceSerializer,
)
from .services import MarketplaceError, confirm_order, recommend_addons


def _is_admin(user) -> bool:
    return user.is_staff or user.role == user.Role.ADMIN


def _provider_for(user) -> AddonProvider | None:
    return getattr(user, "addon_provider", None) or None


class ProviderRegistrationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(settings, "MARKETPLACE_ENABLED", True):
            return Response(
                {"detail": "The add-on marketplace is not enabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        existing = _provider_for(request.user)
        if existing is not None and existing.status in (
            AddonProvider.Status.PENDING,
            AddonProvider.Status.ACTIVE,
        ):
            return Response(AddonProviderSerializer(existing).data)

        provider = AddonProvider.objects.create(
            user=request.user,
            business_name=request.data.get("business_name", ""),
            description=request.data.get("description", ""),
            commission_rate=request.data.get("commission_rate"),
        )
        create_notification(
            user=request.user,
            notification_type=Notification.Type.ADDON_PROVIDER_SUBMITTED,
            title="Provider application submitted",
            message="Your provider application is under review.",
            action_url="/dashboard?tab=marketplace",
        )
        log_action(actor=request.user, action="marketplace.provider_submitted", target=provider)
        return Response(AddonProviderSerializer(provider).data, status=status.HTTP_201_CREATED)


class ProviderMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        provider = _provider_for(request.user)
        if provider is None:
            return Response({"detail": "No provider profile."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AddonProviderSerializer(provider).data)

    def put(self, request):
        provider = _provider_for(request.user)
        if provider is None:
            return Response({"detail": "No provider profile."}, status=status.HTTP_404_NOT_FOUND)
        if request.data.get("business_name") is not None:
            provider.business_name = request.data["business_name"]
        if request.data.get("description") is not None:
            provider.description = request.data["description"]
        if request.data.get("commission_rate") is not None:
            provider.commission_rate = request.data["commission_rate"]
        provider.save()
        return Response(AddonProviderSerializer(provider).data)


class AddonServiceListView(APIView):
    """List services (public, active only); providers may create services."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = AddonService.objects.filter(
            is_active=True, provider__status=AddonProvider.Status.ACTIVE
        )
        category = request.query_params.get("category")
        if category in AddonService.Category.values:
            queryset = queryset.filter(category=category)
        return Response(AddonServiceSerializer(queryset.select_related("provider"), many=True).data)

    def post(self, request):
        provider = _provider_for(request.user)
        if provider is None or provider.status != AddonProvider.Status.ACTIVE:
            return Response(
                {"detail": "An active provider profile is required."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AddonServiceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        service = serializer.save(provider=provider)
        log_action(actor=request.user, action="marketplace.service_created", target=service)
        return Response(AddonServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class AddonServiceDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        service = self._get_service(pk)
        if service is None:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AddonServiceSerializer(service).data)

    def put(self, request, pk):
        service = self._get_service(pk)
        if service is None:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)
        if service.provider.user_id != request.user.id and not _is_admin(request.user):
            return Response(
                {"detail": "Only the owning provider can edit this service."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AddonServiceSerializer(service, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(AddonServiceSerializer(service).data)

    def _get_service(self, pk):
        try:
            return AddonService.objects.select_related("provider").get(pk=pk)
        except (AddonService.DoesNotExist, TypeError, ValueError):
            return None


class AddonOrderListView(APIView):
    """Tenants create/list their orders; providers see orders for their services."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        provider = _provider_for(request.user)
        if provider is not None and not _is_admin(request.user):
            queryset = AddonOrder.objects.filter(service__provider=provider)
        else:
            queryset = AddonOrder.objects.filter(tenant=request.user)
        return Response(
            AddonOrderSerializer(
                queryset.select_related("service", "tenant", "broker"), many=True
            ).data
        )

    def post(self, request):
        if not getattr(settings, "MARKETPLACE_ENABLED", True):
            return Response(
                {"detail": "The add-on marketplace is not enabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AddonOrderSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        order = serializer.save()
        return Response(AddonOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class AddonOrderActionView(APIView):
    """confirm (provider) / cancel (tenant) on an order."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = AddonOrder.objects.select_related("service__provider").get(pk=pk)
        except (AddonOrder.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        action = request.query_params.get("action") or request.data.get("action")
        if action == "confirm":
            provider = _provider_for(request.user)
            if (provider is None or order.service.provider_id != provider.id) and not _is_admin(
                request.user
            ):
                return Response(
                    {"detail": "Only the providing service can confirm this order."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                order = confirm_order(order, request.user)
            except MarketplaceError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(AddonOrderSerializer(order).data)

        if action == "cancel":
            if order.tenant_id != request.user.id and not _is_admin(request.user):
                return Response(
                    {"detail": "Only the tenant can cancel this order."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if order.status != AddonOrder.Status.PENDING:
                return Response(
                    {"detail": f"Cannot cancel a {order.status} order."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                order.status = AddonOrder.Status.CANCELED
                order.save(update_fields=["status", "updated_at"])
            return Response(AddonOrderSerializer(order).data)

        return Response(
            {"detail": "action must be 'confirm' or 'cancel'."}, status=status.HTTP_400_BAD_REQUEST
        )


class MarketplaceRecommendView(APIView):
    """Cross-sell add-ons for a booking (tenant, room owner, or admin)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from bookings.models import Booking

        booking_id = request.query_params.get("booking_id")
        try:
            booking = Booking.objects.get(pk=booking_id)
        except (Booking.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        allowed = (
            booking.tenant_id == request.user.id
            or booking.room.owner_id == request.user.id
            or _is_admin(request.user)
        )
        if not allowed:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        services = recommend_addons(booking)
        reasons = {s.category: "recommended for new leases" for s in services}
        return Response(
            {
                "booking_id": booking.pk,
                "services": AddonServiceSerializer(services, many=True).data,
                "reasons": reasons,
            }
        )
