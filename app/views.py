"""
Vistas de la aplicación app.
Incluye la Landing Page y el módulo completo de Autenticación y Gestión de Cuentas.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_http_methods

from .forms import (
    CustomAuthenticationForm,
    CustomPasswordResetForm,
    CustomSetPasswordForm,
    CustomUserCreationForm,
    ResendActivationForm,
)
from .utils import send_activation_email

CustomUser = get_user_model()


def home(request):
    """Renderiza la Landing Page (app/home.html) directamente sin realizar consultas a PostgreSQL."""
    return render(request, "app/home.html")


class CustomLoginView(LoginView):
    """Vista de inicio de sesión con formulario basado en email y redirección si ya está autenticado."""

    template_name = "app/auth/login.html"
    authentication_form = CustomAuthenticationForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    """Vista de cierre de sesión restringida exclusivamente al método POST."""

    http_method_names = ["post", "options"]
    next_page = reverse_lazy("app:login")


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Vista de registro de nuevos usuarios.
    Crea la cuenta con is_active=False y despacha el correo de confirmación.
    """
    if request.user.is_authenticated:
        return redirect("app:home")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            send_activation_email(request, user)
            return redirect("app:verify_email_sent")
    else:
        form = CustomUserCreationForm()

    return render(request, "app/auth/register.html", {"form": form})


@require_http_methods(["GET"])
def verify_email_sent_view(request):
    """Vista informativa tras enviar el enlace de activación por correo electrónico."""
    return render(request, "app/auth/verify_email_sent.html")


@require_http_methods(["GET"])
def activate_account_view(request, uidb64, token):
    """
    Verifica el token de activación enviado por correo electrónico.
    Si es válido, activa la cuenta y redirige al login; de lo contrario, muestra error.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        messages.success(
            request,
            "Cuenta activada correctamente. Ya puede iniciar sesión.",
        )
        return redirect("app:login")

    return render(request, "app/auth/verify_email_invalid.html", status=400)


@require_http_methods(["GET", "POST"])
def resend_activation_view(request):
    """
    Permite solicitar un nuevo enlace de activación para cuentas inactivas.
    Implementa rate-limit en memoria (120 segundos) y protección contra enumeración.
    """
    if request.method == "POST":
        form = ResendActivationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            cache_key = f"resend_cooldown_{email}"

            if cache.get(cache_key):
                cooldown_msg = (
                    "Debe aguardar 2 minutos antes de solicitar otro enlace de activación."
                )
                form.add_error(None, cooldown_msg)
                messages.error(request, cooldown_msg)
                return render(
                    request,
                    "app/auth/resend_activation.html",
                    {"form": form},
                )

            user = CustomUser.objects.filter(
                email__iexact=email, is_active=False
            ).first()
            if user is not None:
                send_activation_email(request, user)
                cache.set(cache_key, True, timeout=120)

            return redirect("app:verify_email_sent")
    else:
        initial_email = request.GET.get("email", "").strip().lower()
        form = ResendActivationForm(
            initial={"email": initial_email} if initial_email else None
        )

    return render(request, "app/auth/resend_activation.html", {"form": form})


class CustomPasswordResetView(PasswordResetView):
    """Paso 1: Solicitud de recuperación de contraseña por correo electrónico."""

    template_name = "app/auth/password_reset_form.html"
    email_template_name = "app/auth/emails/password_reset_email.txt"
    subject_template_name = "app/auth/emails/password_reset_subject.txt"
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy("app:password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Paso 2: Confirmación de despacho de instrucciones de recuperación."""

    template_name = "app/auth/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Paso 3: Ingreso de la nueva contraseña validando UID y token."""

    template_name = "app/auth/password_reset_confirm.html"
    form_class = CustomSetPasswordForm
    success_url = reverse_lazy("app:password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Paso 4: Confirmación final de restablecimiento de contraseña."""

    template_name = "app/auth/password_reset_complete.html"
