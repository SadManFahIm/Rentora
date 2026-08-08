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
from users import otp_views as users_otp_views
from users import passkey_views as users_passkey_views

urlpatterns = [
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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
