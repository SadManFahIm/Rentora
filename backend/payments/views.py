import logging

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.utils import create_notification
from notifications.models import Notification

from .models import Payment
from .serializers import PaymentInitiateSerializer, PaymentSerializer
from .services import bkash as bkash_service
from .services import sslcommerz as sslcommerz_service
from .services.bkash import BkashError
from .services.receipt import generate_receipt_pdf
from .services.sslcommerz import SSLCommerzError

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
    """The tenant who made the payment — used for history/receipt access."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id


class IsBookingLandlord(permissions.BasePermission):
    """The landlord who owns the booked room — the only party allowed to
    issue a refund for a payment made against their room."""

    def has_object_permission(self, request, view, obj):
        return obj.booking.room.owner_id == request.user.id


@extend_schema_view(
    list=extend_schema(tags=["Payments"], summary="List my payment history"),
    retrieve=extend_schema(tags=["Payments"], summary="Retrieve a payment (owner only)"),
)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only payment history, plus owner/landlord actions (receipt, refund)."""

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsPaymentOwner]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payment.objects.none()
        base = Payment.objects.select_related("booking", "booking__room", "booking__room__owner", "user")
        if self.action == "refund":
            # The refund actor is the room's landlord, not the payment's own
            # `user` (the tenant who paid) — so this action must not be
            # scoped down to `user=request.user` like every other action.
            return base
        return base.filter(user=self.request.user)

    def get_permissions(self):
        if self.action == "refund":
            return [permissions.IsAuthenticated(), IsBookingLandlord()]
        return [permissions.IsAuthenticated(), IsPaymentOwner()]

    @extend_schema(tags=["Payments"], summary="Download a PDF receipt (owner only)")
    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        payment = self.get_object()
        if payment.status != Payment.Status.SUCCESS:
            return Response(
                {"detail": "A receipt is only available for successful payments."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = generate_receipt_pdf(payment)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="receipt-{payment.transaction_id}.pdf"'
        return response

    @extend_schema(tags=["Payments"], summary="Refund a payment (landlord only)")
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        payment = self.get_object()

        if payment.status != Payment.Status.SUCCESS:
            return Response(
                {"detail": "Only successful payments can be refunded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_amount = request.data.get("amount")
        try:
            refund_amount = float(requested_amount) if requested_amount is not None else float(payment.amount)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid refund amount."}, status=status.HTTP_400_BAD_REQUEST)

        # Never trust a client-supplied refund amount beyond capping it at
        # what was actually paid — no partial-refund-turned-overpayment.
        if refund_amount <= 0 or refund_amount > float(payment.amount):
            return Response(
                {"detail": "Refund amount must be between 0 and the original payment amount."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status != Payment.Status.SUCCESS:
                return Response(
                    {"detail": "Only successful payments can be refunded."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                if payment.payment_method == Payment.Method.BKASH:
                    bkash_payment_id = payment.gateway_response.get("paymentID")
                    result = bkash_service.refund_payment(
                        bkash_payment_id, payment.gateway_transaction_id, str(refund_amount)
                    )
                elif payment.payment_method == Payment.Method.SSLCOMMERZ:
                    result = sslcommerz_service.refund_payment(
                        payment.gateway_transaction_id, str(refund_amount)
                    )
                else:
                    return Response(
                        {"detail": f"Refunds are not supported for payment method '{payment.payment_method}'."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except (BkashError, SSLCommerzError) as exc:
                logger.error("Refund failed for payment %s: %s", payment.transaction_id, exc)
                return Response(
                    {"detail": "Refund could not be processed by the gateway.", "error": str(exc)},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            payment.status = Payment.Status.REFUNDED
            payment.gateway_response = {**payment.gateway_response, "refund": result}
            payment.save(update_fields=["status", "gateway_response", "updated_at"])

        return Response({"detail": "Payment refunded.", "transaction_id": payment.transaction_id})


class PaymentInitiateView(APIView):
    """Start an SSLCommerz payment: validate the booking, create a Payment
    record, open an SSLCommerz session, and hand back the gateway URL.

    The amount is never taken from the client — it is always the booking's
    own `monthly_rent`, so a tampered request body cannot under/overcharge.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Payments"], request=PaymentInitiateSerializer, summary="Initiate an SSLCommerz payment")
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
            session = sslcommerz_service.initiate_payment(payment, success_url, fail_url, cancel_url)
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


class BkashInitiateView(APIView):
    """Start a bKash payment: same booking/ownership/amount rules as the
    SSLCommerz initiate view above, just against a different gateway."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Payments"], request=PaymentInitiateSerializer, summary="Initiate a bKash payment")
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
            payment_method=Payment.Method.BKASH,
            status=Payment.Status.INITIATED,
        )

        # Our own transaction_id rides along as a query param so the callback
        # can identify the Payment row directly, without needing to look it
        # up by bKash's own paymentID.
        callback_url = (
            request.build_absolute_uri(reverse("payment-bkash-callback"))
            + f"?tran_id={payment.transaction_id}"
        )

        try:
            session = bkash_service.create_payment(payment, callback_url)
        except BkashError as exc:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = str(exc)
            payment.save(update_fields=["status", "failure_reason", "updated_at"])
            return Response(
                {"detail": "Could not start bKash payment session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.status = Payment.Status.PENDING
        payment.gateway_response = session
        payment.save(update_fields=["status", "gateway_response", "updated_at"])

        return Response(
            {"bkash_url": session["bkashURL"], "transaction_id": payment.transaction_id},
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
            validation = sslcommerz_service.validate_payment(val_id)
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


class BkashCallbackView(APIView):
    """bKash redirects the user's browser here (GET) after checkout, with
    `paymentID` and its own `status` hint (success/failure/cancel) as query
    params.

    CRITICAL: `status` is just a redirect hint from the user's own browser —
    exactly as forgeable as any other client-supplied value — so it is never
    trusted directly. `query_payment()` against bKash's own API is the only
    source of truth for whether the transaction actually completed.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Payments"], summary="bKash checkout callback")
    def get(self, request):
        tran_id = request.query_params.get("tran_id")
        payment_id = request.query_params.get("paymentID")

        if not tran_id or not payment_id:
            return self._redirect("failed", tran_id)

        try:
            payment = Payment.objects.get(transaction_id=tran_id)
        except Payment.DoesNotExist:
            return self._redirect("failed", tran_id)

        # Idempotency fast path — mirrors the SSLCommerz callback: once
        # settled, no further callback (genuine retry or forged replay) may
        # touch this payment again.
        if payment.status in TERMINAL_STATUSES:
            outcome = "success" if payment.status == Payment.Status.SUCCESS else "failed"
            return self._redirect(outcome, tran_id)

        try:
            query_result = bkash_service.query_payment(payment_id)
        except BkashError as exc:
            logger.error("bKash query_payment failed for tran_id=%s: %s", tran_id, exc)
            return self._redirect("failed", tran_id)

        transaction_status = query_result.get("transactionStatus")

        if transaction_status != "Completed":
            # bKash's own records say this was never completed (Initiated /
            # Failed / user backed out) — regardless of what the redirect's
            # `status` query param claimed.
            mutated = False
            with transaction.atomic():
                try:
                    payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
                except Payment.DoesNotExist:
                    return self._redirect("failed", tran_id)
                if payment.status not in TERMINAL_STATUSES:
                    payment.status = Payment.Status.FAILED
                    payment.failure_reason = f"bKash transactionStatus={transaction_status}"
                    payment.gateway_response = {**payment.gateway_response, "query": query_result}
                    payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])
                    mutated = True
            if mutated:
                _notify_payment_result(payment, success=False)
            return self._redirect("failed", tran_id)

        # bKash confirms the checkout was completed — finalize it by
        # executing the payment (bKash's two-step tokenized checkout flow).
        try:
            execute_result = bkash_service.execute_payment(payment_id)
        except BkashError as exc:
            logger.error("bKash execute_payment failed for tran_id=%s: %s", tran_id, exc)
            return self._redirect("failed", tran_id)

        if execute_result.get("transactionStatus") != "Completed":
            mutated = False
            with transaction.atomic():
                try:
                    payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
                except Payment.DoesNotExist:
                    return self._redirect("failed", tran_id)
                if payment.status not in TERMINAL_STATUSES:
                    payment.status = Payment.Status.FAILED
                    payment.failure_reason = execute_result.get("statusMessage") or "bKash execute did not complete."
                    payment.gateway_response = {**payment.gateway_response, "execute": execute_result}
                    payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])
                    mutated = True
            if mutated:
                _notify_payment_result(payment, success=False)
            return self._redirect("failed", tran_id)

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(transaction_id=tran_id)
            except Payment.DoesNotExist:
                return self._redirect("failed", tran_id)

            # Re-check under the row lock in case a concurrent callback hit
            # already settled this transaction while we were talking to bKash.
            if payment.status in TERMINAL_STATUSES:
                outcome = "success" if payment.status == Payment.Status.SUCCESS else "failed"
                return self._redirect(outcome, tran_id)

            executed_amount = execute_result.get("amount")
            if executed_amount is not None and abs(float(executed_amount) - float(payment.amount)) > 0.01:
                payment.status = Payment.Status.FAILED
                payment.failure_reason = (
                    f"Amount mismatch: expected {payment.amount}, bKash executed {executed_amount}"
                )
                payment.gateway_response = {**payment.gateway_response, "execute": execute_result}
                payment.save(update_fields=["status", "failure_reason", "gateway_response", "updated_at"])
                logger.error("bKash amount mismatch on tran_id=%s", tran_id)
                _notify_payment_result(payment, success=False)
                return self._redirect("failed", tran_id)

            payment.status = Payment.Status.SUCCESS
            payment.gateway_transaction_id = execute_result.get("trxID", "")
            payment.gateway_response = {**payment.gateway_response, "execute": execute_result}
            payment.save(
                update_fields=["status", "gateway_transaction_id", "gateway_response", "updated_at"]
            )

        _notify_payment_result(payment, success=True)
        return self._redirect("success", tran_id)

    @staticmethod
    def _redirect(outcome: str, tran_id: str | None):
        url = f"{settings.FRONTEND_URL}/payment/{outcome}"
        if tran_id:
            url += f"?transaction_id={tran_id}"
        return redirect(url)
