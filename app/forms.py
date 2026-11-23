"""
Formularios de autenticación y gestión de cuentas para la aplicación app.
Cumple con la estética estoica (class="form-input") y normalización estricta de emails.
"""

from decimal import Decimal
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)
from django.db.models import Q
from django.template import loader

from .models import (
    Client,
    Cliente,
    MAX_PDF_SIZE_BYTES,
    Transaction,
    Vertical,
    normalize_vertical_title_key,
)
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


def resolve_or_create_client(user, raw_value):
    """
    Resuelve un cliente perteneciente a `user` a partir de su ID numérico o su nombre.
    Si se proporciona un nombre que aún no existe para el usuario, lo crea automáticamente
    y retorna la instancia con su ID asignado.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if raw_value is None:
        return None
    if isinstance(raw_value, Cliente):
        return raw_value if raw_value.user_id == user.id else None

    val_str = str(raw_value).strip()
    if not val_str or val_str.lower() in ("nan", "none", "-", "— sin cliente —", "sin cliente"):
        return None

    if val_str.isdigit():
        by_id = Cliente.objects.filter(user=user, pk=int(val_str)).first()
        if by_id is not None:
            return by_id

    existing = Cliente.objects.filter(user=user, nombre_completo__iexact=val_str).first()
    if existing is not None:
        return existing

    return Cliente.objects.create(user=user, nombre_completo=val_str[:150])


class ClienteForm(forms.ModelForm):
    """
    ModelForm para la creación y edición de registros de Cliente.
    Valida estrictamente que la documentación adjunta sea un archivo .pdf
    y no supere los 10 MB (10.485.760 bytes).
    """

    MAX_PDF_BYTES = MAX_PDF_SIZE_BYTES  # 10.485.760 bytes (10 MB)

    class Meta:
        model = Cliente
        fields = ("nombre_completo", "email", "telefono", "sexo", "documentacion")
        widgets = {
            "nombre_completo": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Nombre y Apellido / Razón Social",
                    "maxlength": "150",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "cliente@empresa.com",
                }
            ),
            "telefono": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "+54 9 11 0000-0000",
                    "maxlength": "50",
                }
            ),
            "sexo": forms.Select(
                attrs={
                    "class": "form-input",
                }
            ),
            "documentacion": forms.ClearableFileInput(
                attrs={
                    "class": "form-input file-input-stoic",
                    "accept": ".pdf,application/pdf",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        data = kwargs.get("data")
        if data is None and len(args) > 0:
            data = args[0]

        if data is not None:
            mutable = data.copy() if hasattr(data, "copy") else dict(data)
            raw_sexo = str(mutable.get("sexo") or "").strip().upper()
            if raw_sexo in ("M", "MASCULINO"):
                mutable["sexo"] = Cliente.Sexo.MASCULINO
            elif raw_sexo in ("F", "FEMENINO"):
                mutable["sexo"] = Cliente.Sexo.FEMENINO
            elif raw_sexo in ("OTRO", "OTROS", "X", ""):
                mutable["sexo"] = Cliente.Sexo.OTRO

            if len(args) > 0:
                args = (mutable,) + args[1:]
            else:
                kwargs["data"] = mutable

        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["telefono"].required = False
        self.fields["sexo"].required = False
        self.fields["documentacion"].required = False

    def clean_nombre_completo(self):
        nombre = (self.cleaned_data.get("nombre_completo") or "").strip()
        if not nombre:
            raise forms.ValidationError("El nombre completo del cliente es obligatorio.")
        if self.user is not None and self.user.is_authenticated:
            qs = Cliente.objects.filter(
                user=self.user, nombre_completo__iexact=nombre
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "Ya existe un cliente registrado con este nombre."
                )
        return nombre

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_telefono(self):
        return (self.cleaned_data.get("telefono") or "").strip()

    def clean_sexo(self):
        sexo = (self.cleaned_data.get("sexo") or "").strip()
        if not sexo:
            return Cliente.Sexo.OTRO
        return sexo

    def clean_documentacion(self):
        archivo = self.cleaned_data.get("documentacion")
        if not archivo:
            return None

        # Validar solo cuando se sube un archivo nuevo o modificado
        filename = (getattr(archivo, "name", "") or "").lower().strip()
        if not filename.endswith(".pdf"):
            raise forms.ValidationError(
                "Formato inválido: Solo se permiten archivos con extensión .pdf."
            )

        file_size = getattr(archivo, "size", 0) or 0
        if file_size > self.MAX_PDF_BYTES:
            raise forms.ValidationError(
                "El archivo PDF supera el límite máximo permitido de 10 MB (10.485.760 bytes)."
            )

        return archivo

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user is not None and getattr(self.user, "is_authenticated", False):
            instance.user = self.user
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class VerticalForm(forms.ModelForm):
    """
    ModelForm para dar de alta y actualizar Verticales de negocio.
    Implementa normalización estricta con .strip(), unicidad case-insensitive
    entre verticales activas del usuario y reactivación controlada si existe
    una vertical previamente dada de baja con el mismo título.
    """

    class Meta:
        model = Vertical
        fields = ("title", "description")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Ej: Consultoría Financiera",
                    "maxlength": "120",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "placeholder": "Descripción operativa de la vertical de negocio",
                    "rows": "2",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.reactivated_instance = None
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False

    def clean_title(self):
        raw_title = (self.cleaned_data.get("title") or "").strip()
        title = " ".join(raw_title.split())
        if not title:
            raise forms.ValidationError("El título de la vertical es obligatorio.")

        if self.user is not None and self.user.is_authenticated:
            target_key = normalize_vertical_title_key(title)
            active_qs = Vertical.objects.filter(
                user=self.user, is_active=True
            )
            if self.instance and self.instance.pk:
                active_qs = active_qs.exclude(pk=self.instance.pk)
            for existing in active_qs:
                if (
                    existing.title.strip().lower() == title.lower()
                    or normalize_vertical_title_key(existing.title)
                    == target_key
                ):
                    raise forms.ValidationError(
                        "Ya existe una vertical activa con este título."
                    )

            if not (self.instance and self.instance.pk):
                inactive_qs = Vertical.objects.filter(
                    user=self.user, is_active=False
                ).order_by("-id")
                for inactive in inactive_qs:
                    if (
                        inactive.title.strip().lower() == title.lower()
                        or normalize_vertical_title_key(inactive.title)
                        == target_key
                    ):
                        self.reactivated_instance = inactive
                        break
        return title

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()

    def save(self, commit=True):
        if self.reactivated_instance is not None:
            instance = self.reactivated_instance
            instance.title = self.cleaned_data["title"]
            new_desc = self.cleaned_data.get("description", "")
            if new_desc:
                instance.description = new_desc
            instance.is_active = True
            instance.deactivated_at = None
            if commit:
                instance.save()
            self.instance = instance
            return instance

        instance = super().save(commit=False)
        if self.user is not None and self.user.is_authenticated:
            instance.user = self.user
        instance.is_active = True
        instance.deactivated_at = None
        if commit:
            instance.save()
        return instance


class VerticalChoiceField(forms.ModelChoiceField):
    """
    ModelChoiceField que etiqueta visualmente como '(Inactiva)' cualquier vertical
    dada de baja que permanezca asociada a una transacción histórica en edición.
    """

    def label_from_instance(self, obj):
        if not obj.is_active:
            return f"{obj.title} (Inactiva)"
        return obj.title


def resolve_user_vertical_input(user, raw_value, instance=None):
    """
    Resuelve el valor entrante para `vertical` en TransactionForm:
    - Si está vacío: devuelve "".
    - Si es un ID numérico perteneciente al usuario: devuelve ese ID.
    - Si es un título (string): busca en las verticales del usuario (priorizando activas);
      si coincide con una vertical del usuario (activa o inactiva), devuelve su PK para que
      el validador de formulario evalúe si está activa o si es conservación histórica.
      Si no existe en la cuenta del usuario, retorna un marcador inválido para rechazarlo.
    """
    if raw_value is None:
        return ""
    if isinstance(raw_value, Vertical):
        return str(raw_value.pk)

    val_str = " ".join(str(raw_value).strip().split())
    if not val_str or val_str.lower() in (
        "nan",
        "none",
        "-",
        "— sin vertical —",
        "sin vertical",
    ):
        return ""

    if user is None or not getattr(user, "is_authenticated", False):
        return val_str

    if val_str.isdigit():
        return val_str

    # Permitir que el título venga con el sufijo "(Inactiva)" desde la UI
    cleaned_title = val_str
    if cleaned_title.lower().endswith("(inactiva)"):
        cleaned_title = cleaned_title[: -len("(inactiva)")].strip()

    target_key = normalize_vertical_title_key(cleaned_title)
    user_verticals = list(
        Vertical.objects.filter(user=user).order_by("-is_active", "-id")
    )
    for v in user_verticals:
        if (
            v.title.strip().lower() == cleaned_title.lower()
            or normalize_vertical_title_key(v.title) == target_key
        ):
            return str(v.pk)

    return "__INVALID_VERTICAL__"


class TransactionForm(forms.ModelForm):
    """
    ModelForm para la creación y edición de registros de Transaction con la estructura
    contable de 8 campos: Fecha, Vertical (FK PROTECT), Tipo, Concepto, Cliente, Detalle, Monto y Moneda.
    Valida estrictamente que la vertical seleccionada pertenezca al usuario y esté activa,
    salvo cuando se preserva la vertical histórica inactiva de una transacción ya existente.
    """

    vertical = VerticalChoiceField(
        queryset=Vertical.objects.none(),
        required=False,
        empty_label="— Sin vertical —",
        widget=forms.Select(attrs={"class": "sheet-select"}),
        error_messages={
            "invalid_choice": "La vertical seleccionada no existe, no pertenece a su cuenta o fue dada de baja.",
        },
    )

    class Meta:
        model = Transaction
        fields = (
            "date",
            "vertical",
            "transaction_type",
            "concept",
            "client",
            "detail",
            "amount",
            "currency",
        )
        widgets = {
            "date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "sheet-input"},
            ),
            "transaction_type": forms.Select(
                attrs={"class": "sheet-select"},
            ),
            "concept": forms.TextInput(
                attrs={
                    "class": "sheet-input",
                    "placeholder": "Tipo de ingreso o gasto",
                },
            ),
            "client": forms.Select(
                attrs={"class": "sheet-select"},
            ),
            "detail": forms.TextInput(
                attrs={
                    "class": "sheet-input",
                    "placeholder": "Detalle adicional",
                },
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "sheet-input sheet-input--num",
                    "step": "0.01",
                    "min": "0.01",
                    "placeholder": "0.00",
                },
            ),
            "currency": forms.Select(
                attrs={"class": "sheet-select"},
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        instance = kwargs.get("instance")
        if self.user is None and instance is not None and instance.user_id:
            self.user = instance.user

        self._original_vertical_id = (
            instance.vertical_id if (instance and instance.pk) else None
        )
        self._rejected_inactive_vertical = False
        self._rejected_foreign_or_missing_vertical = False

        data = kwargs.get("data")
        if data is None and len(args) > 0:
            data = args[0]

        if data is not None:
            mutable = data.copy() if hasattr(data, "copy") else dict(data)
            raw_type = str(mutable.get("transaction_type") or "").strip().upper()
            if raw_type in ("GASTO", "GASTOS", "EGRESO", "EGRESOS", "E", "G", "EXPENSE"):
                mutable["transaction_type"] = Transaction.TransactionType.EXPENSE
            elif raw_type in ("INGRESO", "INGRESOS", "I", "INCOME"):
                mutable["transaction_type"] = Transaction.TransactionType.INCOME

            raw_currency = str(mutable.get("currency") or "").strip().upper()
            if not raw_currency:
                mutable["currency"] = Transaction.Currency.ARS
            elif raw_currency in ("ARS", "$", "PESO", "PESOS"):
                mutable["currency"] = Transaction.Currency.ARS
            elif raw_currency in ("USD", "U$S", "US$", "DOLAR", "DOLARES", "DÓLAR", "DÓLARES"):
                mutable["currency"] = Transaction.Currency.USD

            raw_client = mutable.get("client")
            if not raw_client and mutable.get("client_name"):
                raw_client = mutable.get("client_name")
            if self.user is not None and getattr(self.user, "is_authenticated", False) and raw_client:
                resolved_client = resolve_or_create_client(self.user, raw_client)
                mutable["client"] = resolved_client.pk if resolved_client else ""
            elif not raw_client:
                mutable["client"] = ""

            raw_vertical = mutable.get("vertical")
            if (raw_vertical is None or raw_vertical == "") and mutable.get("vertical_id"):
                raw_vertical = mutable.get("vertical_id")
            resolved_vertical = resolve_user_vertical_input(
                self.user, raw_vertical, instance=instance
            )
            if resolved_vertical == "__INVALID_VERTICAL__":
                self._rejected_foreign_or_missing_vertical = True
                mutable["vertical"] = ""
            elif resolved_vertical.isdigit() and self.user is not None:
                v_id = int(resolved_vertical)
                v_obj = Vertical.objects.filter(pk=v_id, user=self.user).first()
                if v_obj is None:
                    self._rejected_foreign_or_missing_vertical = True
                    mutable["vertical"] = ""
                elif not v_obj.is_active and v_obj.id != self._original_vertical_id:
                    self._rejected_inactive_vertical = True
                    mutable["vertical"] = ""
                else:
                    mutable["vertical"] = str(v_obj.id)
            else:
                mutable["vertical"] = resolved_vertical

            if len(args) > 0:
                args = (mutable,) + args[1:]
            else:
                kwargs["data"] = mutable

        super().__init__(*args, **kwargs)
        self.fields["vertical"].required = False
        self.fields["detail"].required = False
        self.fields["currency"].required = False
        self.fields["client"].required = False
        self.fields["client"].empty_label = "— Sin cliente —"
        self.fields["vertical"].empty_label = "— Sin vertical —"

        target_user_id = (
            self.user.id
            if (self.user is not None and getattr(self.user, "is_authenticated", False))
            else (
                self.instance.user_id
                if (self.instance and self.instance.pk and self.instance.user_id)
                else None
            )
        )

        if target_user_id:
            self.fields["client"].queryset = Client.objects.filter(
                user_id=target_user_id
            ).order_by("name")

            vertical_filter = Q(user_id=target_user_id, is_active=True)
            if self._original_vertical_id:
                vertical_filter |= Q(
                    user_id=target_user_id, pk=self._original_vertical_id
                )
            self.fields["vertical"].queryset = Vertical.objects.filter(
                vertical_filter
            ).order_by("-is_active", "title")
        else:
            self.fields["client"].queryset = Client.objects.none()
            self.fields["vertical"].queryset = Vertical.objects.none()

    def clean_vertical(self):
        if self._rejected_inactive_vertical:
            raise forms.ValidationError(
                "No se puede asignar una vertical dada de baja (inactiva) a la transacción."
            )
        if self._rejected_foreign_or_missing_vertical:
            raise forms.ValidationError(
                "La vertical seleccionada no existe o no pertenece a su cuenta."
            )
        vertical = self.cleaned_data.get("vertical")
        if vertical is None:
            return None
        if self.user is not None and vertical.user_id != self.user.id:
            raise forms.ValidationError(
                "La vertical seleccionada no pertenece a su cuenta."
            )
        if not vertical.is_active and vertical.id != self._original_vertical_id:
            raise forms.ValidationError(
                "No se puede asignar una vertical dada de baja (inactiva) a la transacción."
            )
        return vertical

    def clean_concept(self):
        concept = (self.cleaned_data.get("concept") or "").strip()
        if not concept:
            raise forms.ValidationError("El concepto es obligatorio.")
        return concept

    def clean_detail(self):
        return (self.cleaned_data.get("detail") or "").strip()

    def clean_currency(self):
        currency = (self.cleaned_data.get("currency") or "").strip().upper()
        if not currency:
            return Transaction.Currency.ARS
        if currency not in (Transaction.Currency.ARS, Transaction.Currency.USD):
            raise forms.ValidationError("La moneda debe ser ARS o USD.")
        return currency

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= Decimal("0.00"):
            raise forms.ValidationError("El monto debe ser mayor a cero.")
        return amount.quantize(Decimal("0.01"))

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user is not None and getattr(self.user, "is_authenticated", False):
            instance.user = self.user
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class TransactionBulkUploadForm(forms.Form):
    """
    Formulario para validar la carga de archivos CSV o Excel en memoria (máx. 5 MB).
    """

    MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
    ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")

    file = forms.FileField(
        label="Archivo contable (.csv, .xlsx)",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-input file-input-stoic",
                "accept": ".csv,.xlsx,.xls",
            }
        ),
    )

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if not uploaded:
            raise forms.ValidationError("Debe seleccionar un archivo válido.")
        if uploaded.size > self.MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                "Error de validación: El archivo excede el límite de 5 MB."
            )
        filename = (uploaded.name or "").lower().strip()
        if not filename.endswith(self.ALLOWED_EXTENSIONS):
            raise forms.ValidationError(
                "Formato no admitido. Utilice exclusivamente archivos .csv o .xlsx."
            )
        return uploaded
