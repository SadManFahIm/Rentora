from django.urls import path

from .views import (
    CreditEligibilityView,
    InsuranceProductsView,
    InsuranceQuoteActionView,
    InsuranceQuoteView,
)

urlpatterns = [
    path("insurance/products/", InsuranceProductsView.as_view(), name="insurance-products"),
    path("insurance/quotes/", InsuranceQuoteView.as_view(), name="insurance-quotes"),
    path(
        "insurance/quotes/<int:pk>/action/",
        InsuranceQuoteActionView.as_view(),
        name="insurance-quote-action",
    ),
    path("credit/eligibility/", CreditEligibilityView.as_view(), name="credit-eligibility"),
]
