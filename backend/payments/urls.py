from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BkashCallbackView,
    BkashInitiateView,
    PaymentCancelCallbackView,
    PaymentFailCallbackView,
    PaymentInitiateView,
    PaymentSuccessCallbackView,
    PaymentSummaryView,
    PaymentViewSet,
)

router = DefaultRouter()
router.register("", PaymentViewSet, basename="payment")

urlpatterns = [
    # Explicit paths first — the router's `<pk>/` pattern below would
    # otherwise swallow these as a (nonexistent) payment id.
    path("initiate/", PaymentInitiateView.as_view(), name="payment-initiate"),
    path("summary/", PaymentSummaryView.as_view(), name="payment-summary"),
    path("sslcommerz/success/", PaymentSuccessCallbackView.as_view(), name="payment-sslcommerz-success"),
    path("sslcommerz/fail/", PaymentFailCallbackView.as_view(), name="payment-sslcommerz-fail"),
    path("sslcommerz/cancel/", PaymentCancelCallbackView.as_view(), name="payment-sslcommerz-cancel"),
    path("bkash/initiate/", BkashInitiateView.as_view(), name="payment-bkash-initiate"),
    path("bkash/callback/", BkashCallbackView.as_view(), name="payment-bkash-callback"),
    # router last: provides "" (list), "<pk>/" (retrieve), "<pk>/refund/",
    # "<pk>/receipt/", and "<pk>/invoice/" (the last three via @action on
    # PaymentViewSet).
] + router.urls
