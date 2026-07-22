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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
