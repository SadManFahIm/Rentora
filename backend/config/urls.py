"""
URL configuration for the config project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # dj-rest-auth: login/, logout/, user/ (GET+PUT), token/refresh/ (JWT enabled),
    # password/reset/, password/change/, etc.
    path("api/v1/auth/", include("dj_rest_auth.urls")),
    # dj-rest-auth registration urls.py roots at '', so mounting it at
    # .../register/ gives exactly POST /api/v1/auth/register/.
    path("api/v1/auth/register/", include("dj_rest_auth.registration.urls")),

    path("api/v1/users/", include("users.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
