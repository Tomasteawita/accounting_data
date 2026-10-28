"""Configuración WSGI para el proyecto accounting_data."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "accounting_data.settings")

application = get_wsgi_application()
