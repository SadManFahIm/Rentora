from django.urls import path

from .views import ActiveExperimentsView, ConversionView, ExposureView

urlpatterns = [
    path("active/", ActiveExperimentsView.as_view(), name="experiments-active"),
    path("exposure/", ExposureView.as_view(), name="experiments-exposure"),
    path("conversion/", ConversionView.as_view(), name="experiments-conversion"),
]
