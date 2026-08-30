"""
URL configuration for the config project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from config.auth_views import ThrottledLoginView, ThrottledRegisterView
from config.views import health_check, security_txt
from users import otp_views as users_otp_views
from users import passkey_views as users_passkey_views
from users import sms_otp_views as users_sms_otp_views

urlpatterns = [
    # Health check — no auth, no throttle (load balancer probes).
    path("health/", health_check, name="health-check"),
    # RFC 9116 security.txt — both canonical and convenience paths.
    path(".well-known/security.txt", security_txt, name="security-txt"),
    path("security.txt", security_txt),
    path("admin/", admin.site.urls),
    # API schema & interactive docs.
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/v1/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # Throttled auth endpoints — declared before the dj-rest-auth includes so
    # they take precedence over the un-throttled defaults for the same paths.
    path("api/v1/auth/login/", ThrottledLoginView.as_view(), name="rest_login"),
    path(
        "api/v1/auth/register/",
        ThrottledRegisterView.as_view(),
        name="rest_register",
    ),
    # Email-OTP two-factor authentication (see users/otp_views.py).
    path("api/v1/auth/otp/verify/", users_otp_views.OTPVerifyView.as_view(), name="otp_verify"),
    path("api/v1/auth/otp/resend/", users_otp_views.OTPResendView.as_view(), name="otp_resend"),
    path("api/v1/auth/otp/toggle/", users_otp_views.OTPToggleView.as_view(), name="otp_toggle"),
    path(
        "api/v1/auth/otp/confirm-enable/",
        users_otp_views.OTPConfirmEnableView.as_view(),
        name="otp_confirm_enable",
    ),
    # Phone (SMS) OTP login (see users/sms_otp_views.py) — gated by SMS_OTP_ENABLED.
    path(
        "api/v1/auth/sms/request/",
        users_sms_otp_views.SmsOtpRequestView.as_view(),
        name="sms_otp_request",
    ),
    path(
        "api/v1/auth/sms/verify/",
        users_sms_otp_views.SmsOtpVerifyView.as_view(),
        name="sms_otp_verify",
    ),
    # WebAuthn / passkeys (see users/passkey_views.py).
    path(
        "api/v1/auth/passkey/register/begin/",
        users_passkey_views.PasskeyRegisterBeginView.as_view(),
        name="passkey_register_begin",
    ),
    path(
        "api/v1/auth/passkey/register/complete/",
        users_passkey_views.PasskeyRegisterCompleteView.as_view(),
        name="passkey_register_complete",
    ),
    path(
        "api/v1/auth/passkey/login/begin/",
        users_passkey_views.PasskeyLoginBeginView.as_view(),
        name="passkey_login_begin",
    ),
    path(
        "api/v1/auth/passkey/login/complete/",
        users_passkey_views.PasskeyLoginCompleteView.as_view(),
        name="passkey_login_complete",
    ),
    # dj-rest-auth: logout/, user/ (GET+PUT), token/refresh/ (JWT enabled),
    # password/reset/, password/change/, etc. (login/ overridden above).
    path("api/v1/auth/", include("dj_rest_auth.urls")),
    # dj-rest-auth registration urls.py roots at '', so mounting it at
    # .../register/ gives exactly POST /api/v1/auth/register/ (verify-email,
    # resend-email, etc.); the primary register POST is overridden above.
    path("api/v1/auth/register/", include("dj_rest_auth.registration.urls")),
    path("api/v1/users/", include("users.urls")),
    path("api/v1/rooms/", include("rooms.urls")),
    path("api/v1/", include("bookings.urls")),
    path("api/v1/wishlist/", include("wishlist.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/dashboard/", include("dashboard.urls")),
    path("api/v1/chat/", include("chat.urls")),
    path("api/v1/payments/", include("payments.urls")),
    path("api/v1/recommendations/", include("recommendations.urls")),
    path("api/v1/pricing/", include("pricing.urls")),
    path("api/v1/roommates/", include("roommates.urls")),
    path("api/v1/fraud/", include("fraud.urls")),
    path("api/v1/analytics/", include("analytics.urls")),
    path("api/v1/saved-searches/", include("savedsearches.urls")),
    path("api/v1/copilot/", include("copilot.urls")),
    path("api/v1/moderation/", include("moderation.urls")),
    path("api/v1/disputes/", include("disputes.urls")),
    path("api/v1/audit/", include("audit.urls")),
    path("api/v1/subscriptions/", include("subscriptions.urls")),
    path("api/v1/monetization/", include("monetization.urls")),
    path("api/v1/brokers/", include("brokers.urls")),
    path("api/v1/corporate/", include("corporate.urls")),
    path("api/v1/marketplace/", include("marketplace.urls")),
    path("api/v1/partner-services/", include("partner_services.urls")),
    path("api/v1/flags/", include("feature_flags.urls")),
    path("api/v1/experiments/", include("experiments.urls")),
    # Phase 17 — Graph & Deep Trust
    path("api/v1/ml/", include("ml_models.urls")),
    # Phase 18 — AI Intelligence Layer
    path("api/v1/ai/", include("ai_intelligence.urls")),
    # Phase 19 — Agent SDK foundation
    path("api/v1/agents/", include("agents.urls")),
    # Phase 19.1 — Property Intelligence
    path("api/v1/property-intelligence/", include("property_intelligence.urls")),
]

if settings.DEBUG:
    # Private uploads must never be reachable through the public media URL.
    # They now live in MEDIA_PRIVATE_ROOT (out of MEDIA_ROOT entirely), but a
    # legacy copy in the public root (pre-Phase 16) must still 404 — a hard
    # denial beats "served by the dev static handler by accident".
    from django.http import HttpResponseNotFound

    def _deny_private_media(request, path):
        return HttpResponseNotFound("Not found.")

    urlpatterns += [
        path("media/kyc_documents/<path:path>", _deny_private_media),
        path("media/tenant_kyc/<path:path>", _deny_private_media),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
