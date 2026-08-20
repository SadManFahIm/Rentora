"""Subscription self-serve endpoints: catalog, checkout, cancel, renew.

Checkout mirrors the listing-tier payment flow exactly: the amount is the
server-side ``Plan.price`` (never client-supplied), a ``Payment`` is created
with ``payment_type=subscription`` and the gateway is opened. The
subscription only activates on the gateway success callback (see
``payments.views._apply_success_side_effects`` → ``activate_on_payment``) —
a forged callback can't grant a free plan.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification
from payments.models import Payment
from payments.services import bkash as bkash_service
from payments.services import sslcommerz as sslcommerz_service
from payments.services.bkash import BkashError
from payments.services.sslcommerz import SSLCommerzError
from payments.throttling import PaymentInitiateRateThrottle

from .models import Plan, Subscription
from .serializers import PlanSerializer, SubscriptionSerializer
from .services.entitlements import active_subscription

NON_TERMINAL_STATUSES = (
    Subscription.Status.PENDING,
    Subscription.Status.ACTIVE,
    Subscription.Status.PAST_DUE,
)


def _start_gateway(request, payment: Payment, method: str) -> dict:
    """Open the gateway session; returns the URL payload. Raises on failure."""
    success_url = request.build_absolute_uri(reverse("payment-sslcommerz-success"))
    fail_url = request.build_absolute_uri(reverse("payment-sslcommerz-fail"))
    cancel_url = request.build_absolute_uri(reverse("payment-sslcommerz-cancel"))
    if method == "bkash":
        callback_url = (
            request.build_absolute_uri(reverse("payment-bkash-callback"))
            + f"?tran_id={payment.transaction_id}"
        )
        session = bkash_service.create_payment(payment, callback_url)
        return {"bkash_url": session["bkashURL"], "field": "bkash_url"}
    session = sslcommerz_service.initiate_payment(payment, success_url, fail_url, cancel_url)
    return {"payment_url": session["GatewayPageURL"], "field": "payment_url"}


def _mark_failed(payment: Payment, exc: Exception) -> None:
    payment.failure_reason = str(exc)
    payment.transition_status(
        Payment.Status.FAILED,
        changed_by="system",
        metadata={"error": str(exc)},
        extra_update_fields=["failure_reason"],
    )


class PlanListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(active=True)
        return Response({"plans": PlanSerializer(plans, many=True).data})


class SubscriptionMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PaymentInitiateRateThrottle]

    def get(self, request):
        sub = active_subscription(request.user)
        entitled = (
            list(sub.plan.features)
            if sub is not None
            else list(settings.SUBSCRIPTION_FREE_FEATURES)
        )
        return Response(
            {
                "subscription": SubscriptionSerializer(sub).data if sub else None,
                "entitled_features": entitled,
                "subscriptions_enabled": getattr(settings, "SUBSCRIPTIONS_ENABLED", True),
            }
        )

    def post(self, request):
        if not getattr(settings, "SUBSCRIPTIONS_ENABLED", True):
            return Response(
                {"detail": "Subscriptions are not enabled."}, status=status.HTTP_403_FORBIDDEN
            )

        plan_code = request.data.get("plan_code")
        method = request.data.get("method", "sslcommerz")
        if method not in ("sslcommerz", "bkash"):
            return Response(
                {"method": "method must be 'sslcommerz' or 'bkash'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            plan = Plan.objects.get(code=plan_code, active=True)
        except Plan.DoesNotExist:
            return Response(
                {"plan_code": "Unknown or inactive plan."}, status=status.HTTP_404_NOT_FOUND
            )

        if Subscription.objects.filter(
            user=request.user, status__in=NON_TERMINAL_STATUSES
        ).exists():
            return Response(
                {"detail": "You already have an active subscription. Cancel it first, or renew."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            sub = Subscription.objects.create(
                user=request.user, plan=plan, status=Subscription.Status.PENDING
            )
            payment = Payment.objects.create(
                user=request.user,
                amount=plan.price,
                payment_type=Payment.Type.SUBSCRIPTION,
                payment_method=Payment.Method(method),
                status=Payment.Status.INITIATED,
                subscription=sub,
            )

        try:
            payload = _start_gateway(request, payment, method)
        except (BkashError, SSLCommerzError) as exc:
            _mark_failed(payment, exc)
            with transaction.atomic():
                sub.status = Subscription.Status.CANCELED
                sub.save(update_fields=["status", "updated_at"])
            return Response(
                {"detail": "Could not start payment session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.gateway_response = {"session": payload}
        payment.transition_status(
            Payment.Status.PENDING,
            changed_by="system",
            extra_update_fields=["gateway_response"],
        )
        sub.payment = payment
        sub.save(update_fields=["payment", "updated_at"])

        return Response(
            {
                payload["field"]: payload.get("payment_url") or payload.get("bkash_url"),
                "transaction_id": payment.transaction_id,
                "subscription_id": sub.pk,
            },
            status=status.HTTP_201_CREATED,
        )


class SubscriptionActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PaymentInitiateRateThrottle]

    def get_subscription(self, request, pk):
        try:
            sub = Subscription.objects.select_related("plan").get(pk=pk)
        except Subscription.DoesNotExist:
            return None
        if sub.user_id != request.user.id and not (
            request.user.is_staff or request.user.role == request.user.Role.ADMIN
        ):
            return None
        return sub

    def post(self, request, pk):
        if not getattr(settings, "SUBSCRIPTIONS_ENABLED", True):
            return Response(
                {"detail": "Subscriptions are not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        sub = self.get_subscription(request, pk)
        if sub is None:
            return Response({"detail": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

        action = request.query_params.get("action") or request.data.get("action")
        if action == "cancel":
            return self._cancel(request, sub)
        if action == "renew":
            return self._renew(request, sub)
        return Response(
            {"detail": "action must be 'cancel' or 'renew'."}, status=status.HTTP_400_BAD_REQUEST
        )

    def _cancel(self, request, sub):
        if sub.status == Subscription.Status.PENDING:
            sub.status = Subscription.Status.CANCELED
            sub.save(update_fields=["status", "updated_at"])
        elif sub.status == Subscription.Status.ACTIVE:
            sub.cancel_at_period_end = True
            sub.save(update_fields=["cancel_at_period_end", "updated_at"])
        else:
            return Response(
                {"detail": "This subscription is not active."}, status=status.HTTP_400_BAD_REQUEST
            )
        create_notification(
            user=sub.user,
            notification_type=Notification.Type.SUBSCRIPTION_CANCELED,
            title="Subscription cancelled",
            message=f"Your {sub.plan.name} plan will stop at the end of its current period.",
            action_url="/dashboard?tab=monetization",
        )
        log_action(actor=request.user, action="subscription.canceled", target=sub)
        return Response({"status": sub.status})

    def _renew(self, request, sub):
        if sub.status not in (
            Subscription.Status.ACTIVE,
            Subscription.Status.EXPIRED,
            Subscription.Status.CANCELED,
        ):
            return Response(
                {"detail": "This subscription cannot be renewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        method = request.data.get("method", "sslcommerz")
        if method not in ("sslcommerz", "bkash"):
            return Response(
                {"method": "method must be 'sslcommerz' or 'bkash'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            payment = Payment.objects.create(
                user=request.user,
                amount=sub.plan.price,
                payment_type=Payment.Type.SUBSCRIPTION,
                payment_method=Payment.Method(method),
                status=Payment.Status.INITIATED,
                subscription=sub,
            )

        try:
            payload = _start_gateway(request, payment, method)
        except (BkashError, SSLCommerzError) as exc:
            _mark_failed(payment, exc)
            return Response(
                {"detail": "Could not start payment session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.gateway_response = {"session": payload}
        payment.transition_status(
            Payment.Status.PENDING,
            changed_by="system",
            extra_update_fields=["gateway_response"],
        )
        sub.payment = payment
        sub.save(update_fields=["payment", "updated_at"])

        return Response(
            {
                payload["field"]: payload.get("payment_url") or payload.get("bkash_url"),
                "transaction_id": payment.transaction_id,
                "subscription_id": sub.pk,
            },
            status=status.HTTP_201_CREATED,
        )
