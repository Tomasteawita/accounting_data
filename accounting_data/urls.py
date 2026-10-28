"""Configuración principal de URLs para accounting_data."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("app.urls")),
]
