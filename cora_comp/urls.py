"""CORA-COMP's own routes, mounted by ``deploy/urls.py`` beside the core API."""
from django.urls import path

from . import views

urlpatterns = [
    path("results/", views.results_page, name="cora_results"),
    path("results/data/", views.results_data, name="cora_results_data"),
]
