"""
Configuración de rutas (URLs) para la aplicación app.
"""

from django.urls import path
from . import views

app_name = "app"

urlpatterns = [
    path("", views.home, name="home"),
    # Autenticación y Registro
    path("auth/login/", views.CustomLoginView.as_view(), name="login"),
    path("auth/logout/", views.CustomLogoutView.as_view(), name="logout"),
    path("auth/register/", views.register_view, name="register"),
    # Confirmación y Reenvío de Correo Electrónico
    path(
        "auth/verify-email/sent/",
        views.verify_email_sent_view,
        name="verify_email_sent",
    ),
    path(
        "auth/verify-email/<uidb64>/<token>/",
        views.activate_account_view,
        name="activate_account",
    ),
    path(
        "auth/resend-activation/",
        views.resend_activation_view,
        name="resend_activation",
    ),
    # Recuperación de Contraseña
    path(
        "auth/password-reset/",
        views.CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "auth/password-reset/done/",
        views.CustomPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "auth/password-reset/<uidb64>/<token>/",
        views.CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "auth/password-reset/complete/",
        views.CustomPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
