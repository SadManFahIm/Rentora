from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentCancelCallbackView,
    PaymentFailCallbackView,
    PaymentInitiateView,
    PaymentSuccessCallbackView,
    PaymentViewSet,
)

router = DefaultRouter()
router.register("", PaymentViewSet, basename="payment")

urlpatterns = [
    # Explicit paths first — the router's `<pk>/` pattern below would
    # otherwise swallow these as a (nonexistent) payment id.
    path("initiate/", PaymentInitiateView.as_view(), name="payment-initiate"),
    path("sslcommerz/success/", PaymentSuccessCallbackView.as_view(), name="payment-sslcommerz-success"),
    path("sslcommerz/fail/", PaymentFailCallbackView.as_view(), name="payment-sslcommerz-fail"),
    path("sslcommerz/cancel/", PaymentCancelCallbackView.as_view(), name="payment-sslcommerz-cancel"),
] + router.urls
