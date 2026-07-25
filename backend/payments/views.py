import logging

from django.db import transaction
from django.urls import reverse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.utils import create_notification
from notifications.models import Notification

from .models import Payment
from .serializers import PaymentInitiateSerializer, PaymentSerializer
from .services.sslcommerz import SSLCommerzError, initiate_payment, validate_payment

logger = logging.getLogger(__name__)

# Once a payment leaves initiated/pending, no callback (success/fail/cancel —
# genuine or forged) may mutate it further. This is the idempotency guard:
# it stops both legitimate gateway retries and replayed/forged callbacks from
# flipping an already-settled payment into a different terminal state.
TERMINAL_STATUSES = (
    Payment.Status.SUCCESS,
    Payment.Status.FAILED,
    Payment.Status.CANCELLED,
    Payment.Status.REFUNDED,
)


class IsPaymentOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id


@extend_schema_view(
    list=extend_schema(tags=["Payments"], summary="List my payment history"),
    retrieve=extend_schema(tags=["Payments"], summary="Retrieve a payment (owner only)"),
)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only payment history for the authenticated user."""

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsPaymentOwner]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        return Payment.objects.filter(user=self.request.user).select_related("booking", "user")


class PaymentInitiateView(APIView):
    """Start a payment: validate the booking, create a Payment record, open an
    SSLCommerz session, and hand back the gateway URL to redirect to.

    The amount is never taken from the client — it is always the booking's
    own `monthly_rent`, so a tampered request body cannot under/overcharge.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Payments"], request=PaymentInitiateSerializer, summary="Initiate a payment")
    def post(self, request):
        serializer = PaymentInitiateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.validated_data["booking"]
        payment_type = serializer.validated_data["payment_type"]

        payment = Payment.objects.create(
            booking=booking,
            user=request.user,
            amount=booking.monthly_rent,
            payment_type=payment_type,
            payment_method=Payment.Method.SSLCOMMERZ,
            status=Payment.Status.INITIATED,
        )

        success_url = request.build_absolute_uri(reverse("payment-sslcommerz-success"))
        fail_url = request.build_absolute_uri(reverse("payment-sslcommerz-fail"))
        cancel_url = request.build_absolute_uri(reverse("payment-sslcommerz-cancel"))

        try:
            session = initiate_payment(payment, success_url, fail_url, cancel_url)
        except SSLCommerzError as exc:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = str(exc)
            payment.save(update_fields=["status", "failure_reason", "updated_at"])
            return Response(
                {"detail": "Could not start payment session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.status = Payment.Status.PENDING
        payment.gateway_response = session
        payment.save(update_fields=["status", "gateway_response", "updated_at"])

        return Response(
            {"payment_url": session["GatewayPageURL"], "transaction_id": payment.transaction_id},
            status=status.HTTP_201_CREATED,
        )


def _notify_payment_result(payment: Payment, *, success: bool) -> None:
    booking = payment.booking
    landlord = booking.room.owner

    if success:
        create_notification(
            user=payment.user,
            notification_type=Notification.Type.PAYMENT_SUCCESS,
            title="Payment successful",
            message=f"Your payment of {payment.amount} BDT for '{booking.room.title}' was successful.",
            action_url="/dashboard/bookings",
        )
        create_notification(
            user=landlord,
            notification_type=Notification.Type.PAYMENT_SUCCESS,
            title="Payment received",
            message=f"{payment.user.get_full_name() or payment.user.username} paid {payment.amount} BDT for '{booking.room.title}'.",
            action_url="/dashboard/bookings",
        )
    else:
        create_notification(
            user=payment.user,
            notification_type=Notification.Type.PAYMENT_FAILED,
            title="Payment failed",
            message=f"Your payment of {payment.amount} BDT for '{booking.room.title}' did not go through.",
            action_url="/dashboard/bookings",
        )


class PaymentSuccessCallbackView(APIView):
    """SSLCommerz redirects/POSTs the browser here after a completed payment.

    CRITICAL: the POST body is entirely client-controlled and trivially
    forgeable (anyone can POST `status=VALID` here without ever paying), so
    we never trust it directly — `val_id` is only used to ask SSLCommerz's
    own validation API whether the transaction genuinely succeeded.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Payments"], summary="SSLCommerz success callback")
    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)

    def _handle(self, request):
        tran_id = request.data.get("tran_id") or request.query_params.get("tran_id")
        val_id = request.data.get("val_id") or request.query_params.get("val_id")

        if not tran_id or not val_id:
            return Response({"detail": "Missing tran_id or val_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.get(transaction_id=tran_id)
        except Payment.DoesNotExist:
            return Response({"detail": "Unknown transaction."}, status=status.HTTP_404_NOT_FOUND)

        # Idempotency fast path: skip re-validating with the gateway entirely
        # once a transaction has already settled (success, fail, cancel, or
        # refund) — e.g. the gateway retries the callback, or a forged retry
        # tries to flip an already-cancelled/failed payment to something else.
        if payment.status in TERMINAL_STATUSES:
            return Response({"detail": "Already processed.", "transaction_id": tran_id})

        try:
            validation = validate_payment(val_id)
        except SSLCommerzError as exc:
            logger.error("Validation call failed for tran_id=%s: %s", tran_id, exc)
            return Response({"detail": "Could not validate payment."}, status=status.HTTP_502_BAD_GATEWAY)

        if validation.get("status") not in ("VALID", "VALIDATED"):
            logger.warning("Payment %s failed validation: %s", tran_id, validation.get("status"))
            with transaction.atomic():
                try:
                    payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
                except Payment.DoesNotExist:
                    return Response({"detail": "Unknown transaction."}, status=status.HTTP_404_NOT_FOUND)
                if payment.status not in TERMINAL_STATUSES:
                    payment.status = Payment.Status.FAILED
                    payment.failure_reason = f"Validation returned status={validation.get('status')}"
                    payment.gateway_response = validation
                    payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])
            return Response({"detail": "Payment could not be validated as successful."}, status=status.HTTP_400_BAD_REQUEST)

        # Also confirm the validated amount/currency match what we expect,
        # so a validated-but-mismatched transaction can't be misapplied.
        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
            except Payment.DoesNotExist:
                return Response({"detail": "Unknown transaction."}, status=status.HTTP_404_NOT_FOUND)

            # Re-check under the row lock: another concurrent request may have
            # already settled this transaction between the fast-path check
            # above and acquiring this lock.
            if payment.status in TERMINAL_STATUSES:
                return Response({"detail": "Already processed.", "transaction_id": tran_id})

            validated_amount = validation.get("amount") or validation.get("currency_amount")
            if validated_amount is not None and abs(float(validated_amount) - float(payment.amount)) > 0.01:
                payment.status = Payment.Status.FAILED
                payment.failure_reason = (
                    f"Amount mismatch: expected {payment.amount}, gateway validated {validated_amount}"
                )
                payment.gateway_response = validation
                payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])
                logger.error("Amount mismatch on tran_id=%s", tran_id)
                return Response({"detail": "Amount mismatch."}, status=status.HTTP_400_BAD_REQUEST)

            payment.status = Payment.Status.SUCCESS
            payment.gateway_transaction_id = validation.get("val_id", val_id)
            payment.gateway_response = validation
            payment.save(
                update_fields=["status", "gateway_transaction_id", "gateway_response", "updated_at"]
            )

        _notify_payment_result(payment, success=True)
        return Response({"detail": "Payment confirmed.", "transaction_id": tran_id})


class PaymentFailCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Payments"], summary="SSLCommerz fail callback")
    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)

    def _handle(self, request):
        tran_id = request.data.get("tran_id") or request.query_params.get("tran_id")
        if not tran_id:
            return Response({"detail": "Missing tran_id."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
            except Payment.DoesNotExist:
                return Response({"detail": "Unknown transaction."}, status=status.HTTP_404_NOT_FOUND)

            if payment.status in TERMINAL_STATUSES:
                return Response({"detail": "Already processed.", "transaction_id": tran_id})

            payment.status = Payment.Status.FAILED
            payment.failure_reason = "Gateway reported payment failure."
            payment.gateway_response = dict(request.data)
            payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])

        _notify_payment_result(payment, success=False)
        return Response({"detail": "Payment marked as failed.", "transaction_id": tran_id})


class PaymentCancelCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Payments"], summary="SSLCommerz cancel callback")
    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)

    def _handle(self, request):
        tran_id = request.data.get("tran_id") or request.query_params.get("tran_id")
        if not tran_id:
            return Response({"detail": "Missing tran_id."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
            except Payment.DoesNotExist:
                return Response({"detail": "Unknown transaction."}, status=status.HTTP_404_NOT_FOUND)

            if payment.status in TERMINAL_STATUSES:
                return Response({"detail": "Already processed.", "transaction_id": tran_id})

            payment.status = Payment.Status.CANCELLED
            payment.gateway_response = dict(request.data)
            payment.save(update_fields=["status", "gateway_response", "updated_at"])

        return Response({"detail": "Payment cancelled.", "transaction_id": tran_id})
