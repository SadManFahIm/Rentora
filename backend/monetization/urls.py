from django.urls import path

from .views import (
    PayoutAdminListView,
    PayoutDecisionView,
    PayoutMarkPaidView,
    RevenueDashboardView,
)

urlpatterns = [
    path("revenue/dashboard/", RevenueDashboardView.as_view(), name="revenue-dashboard"),
    path("payouts/requests/", PayoutAdminListView.as_view(), name="payouts-admin-list"),
    path("payouts/<int:pk>/decision/", PayoutDecisionView.as_view(), name="payout-decision"),
    path("payouts/<int:pk>/mark-paid/", PayoutMarkPaidView.as_view(), name="payout-mark-paid"),
]
