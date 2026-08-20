from django.urls import path

from .views import (
    BrokerCommissionsView,
    BrokerDashboardView,
    BrokerPayoutRequestView,
    BrokerPayoutsView,
    BrokerProfileView,
    BrokerRegisterView,
    BrokerReviewView,
)

urlpatterns = [
    path("register/", BrokerRegisterView.as_view(), name="broker-register"),
    path("profile/", BrokerProfileView.as_view(), name="broker-profile"),
    path("dashboard/", BrokerDashboardView.as_view(), name="broker-dashboard"),
    path("commissions/", BrokerCommissionsView.as_view(), name="broker-commissions"),
    path("payouts/", BrokerPayoutsView.as_view(), name="broker-payouts"),
    path("payouts/request/", BrokerPayoutRequestView.as_view(), name="broker-payout-request"),
    path("<int:pk>/review/", BrokerReviewView.as_view(), name="broker-review"),
]
