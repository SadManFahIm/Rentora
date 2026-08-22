from django.urls import path

from .views import (
    AnalyticsSummaryView,
    AnalyticsTaxonomyView,
    CaptureEventView,
    DemandForecastView,
    MarketReportGenerateView,
    MarketReportView,
)

urlpatterns = [
    path("events/", CaptureEventView.as_view(), name="analytics-capture"),
    path("summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("taxonomy/", AnalyticsTaxonomyView.as_view(), name="analytics-taxonomy"),
    path("forecast/", DemandForecastView.as_view(), name="analytics-forecast"),
    path("market-report/", MarketReportView.as_view(), name="analytics-market-report"),
    path(
        "market-report/generate/",
        MarketReportGenerateView.as_view(),
        name="analytics-market-report-generate",
    ),
]
