from django.urls import path

from .views import (
    CorporateAccountDetailView,
    CorporateAccountView,
    CorporateAdminView,
    CorporateBulkBookingView,
    CorporateInvoicesView,
    CorporateMembersView,
)

urlpatterns = [
    path("accounts/", CorporateAccountView.as_view(), name="corporate-accounts"),
    path(
        "accounts/<int:pk>/", CorporateAccountDetailView.as_view(), name="corporate-account-detail"
    ),
    path("accounts/<int:pk>/members/", CorporateMembersView.as_view(), name="corporate-members"),
    path("bulk-booking/", CorporateBulkBookingView.as_view(), name="corporate-bulk-booking"),
    path("invoices/", CorporateInvoicesView.as_view(), name="corporate-invoices"),
    path("admin/", CorporateAdminView.as_view(), name="corporate-admin"),
]
