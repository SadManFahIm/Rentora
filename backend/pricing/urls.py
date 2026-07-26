from django.urls import path

from .views import MarketStatsView, PriceInsightView, PricePredictView

urlpatterns = [
    path("predict/", PricePredictView.as_view(), name="pricing-predict"),
    path("insight/<int:room_id>/", PriceInsightView.as_view(), name="pricing-insight"),
    path("market-stats/", MarketStatsView.as_view(), name="pricing-market-stats"),
]
