from django.urls import path

from .views import AnalyticsSummaryView, CaptureEventView, DemandForecastView

urlpatterns = [
    path("events/", CaptureEventView.as_view(), name="analytics-capture"),
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("forecast/", DemandForecastView.as_view(), name="analytics-forecast"),
]
