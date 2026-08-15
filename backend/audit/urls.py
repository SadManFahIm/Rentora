from django.urls import path

from .views import AuditTrailView

urlpatterns = [
    path("", AuditTrailView.as_view(), name="audit-trail"),
]
