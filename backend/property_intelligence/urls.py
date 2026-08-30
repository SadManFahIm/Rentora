from django.urls import path

from .views import PropertyIntelligenceStaffView, PropertyIntelligenceView

app_name = "property_intelligence"

urlpatterns = [
    path("<int:room_id>/staff/", PropertyIntelligenceStaffView.as_view(), name="staff-detail"),
    path("<int:room_id>/", PropertyIntelligenceView.as_view(), name="detail"),
]
