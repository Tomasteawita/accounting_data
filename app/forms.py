"""
Formularios de autenticación y gestión de cuentas para la aplicación app.
Cumple con la estética estoica (class="form-input") y normalización estricta de emails.
"""

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)
from django.template import loader

from .utils import send_async_email

CustomUser = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """
    Formulario de registro austero que solicita exclusivamente
    correo electrónico, contraseña y confirmación de contraseña.
    """

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "autocomplete": "email",
                "placeholder": "nombre@empresa.com",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "password1" in self.fields:
            self.fields["password1"].label = "Contraseña"
            self.fields["password1"].widget.attrs.update(
                {
                    "class": "form-input",
                    "autocomplete": "new-password",
                }
            )
        if "password2" in self.fields:
            self.fields["password2"].label = "Confirmar contraseña"
            self.fields["password2"].widget.attrs.update(
                {
                    "class": "form-input",
                    "autocomplete": "new-password",
                }
            )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Ya existe un usuario registrado con este correo electrónico.",
                code="unique",
            )
        return email


class CustomUserChangeForm(UserChangeForm):
    """Formulario de edición de usuario para el panel de administración."""

    class Meta:
        model = CustomUser
        fields = ("email", "first_name", "last_name", "is_active", "is_staff")


class CustomAuthenticationForm(AuthenticationForm):
    """
    Formulario de inicio de sesión basado en correo electrónico.
    Detecta explícitamente cuentas con is_active=False cuando las credenciales son válidas.
    """

    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "autocomplete": "email",
                "autofocus": True,
                "placeholder": "nombre@empresa.com",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "autocomplete": "current-password",
            }
        ),
    )

    error_messages = {
        "invalid_login": (
            "Credenciales inválidas. Verifique su correo electrónico y contraseña."
        ),
        "inactive": (
            "Su cuenta aún no ha sido activada. Revise su correo electrónico "
            "o solicite un nuevo enlace de activación."
        ),
    }

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if username:
            return username.lower().strip()
        return username

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if email is not None and password:
            email = email.lower().strip()
            self.cleaned_data["username"] = email

            # Verificar si existe un usuario inactivo con contraseña válida
            candidate = CustomUser.objects.filter(email__iexact=email).first()
            if (
                candidate is not None
                and candidate.check_password(password)
                and not candidate.is_active
            ):
                raise forms.ValidationError(
                    self.error_messages["inactive"],
                    code="inactive",
                )

            self.user_cache = authenticate(
                self.request, username=email, password=password
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

    @property
    def has_inactive_error(self):
        """Indica si el formulario contiene un error de cuenta inactiva (code='inactive')."""
        return any(
            err.code == "inactive" for err in self.non_field_errors().as_data()
        )


class ResendActivationForm(forms.Form):
    """Formulario austero para solicitar el reenvío del enlace de activación."""

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "autocomplete": "email",
                "placeholder": "nombre@empresa.com",
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email") or ""
        return email.lower().strip()


class CustomPasswordResetForm(PasswordResetForm):
    """
    Formulario de solicitud de restablecimiento de contraseña.
    Normaliza el correo electrónico y despacha el correo de forma no bloqueante.
    """

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "autocomplete": "email",
                "placeholder": "nombre@empresa.com",
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email") or ""
        return email.lower().strip()

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """Envía el correo de recuperación utilizando send_async_email."""
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        html_email = (
            loader.render_to_string(html_email_template_name, context)
            if html_email_template_name is not None
            else None
        )
        send_async_email(
            subject=subject,
            body=body,
            to_email=to_email,
            html_message=html_email,
        )


class CustomSetPasswordForm(SetPasswordForm):
    """Formulario para establecer una nueva contraseña con estilos del sistema."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "new_password1" in self.fields:
            self.fields["new_password1"].label = "Nueva contraseña"
            self.fields["new_password1"].widget.attrs.update(
                {
                    "class": "form-input",
                    "autocomplete": "new-password",
                }
            )
        if "new_password2" in self.fields:
            self.fields["new_password2"].label = "Confirmar nueva contraseña"
            self.fields["new_password2"].widget.attrs.update(
                {
                    "class": "form-input",
                    "autocomplete": "new-password",
                }
            )
