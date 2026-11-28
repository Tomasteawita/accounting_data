"""
Modelos de datos para la aplicación app.
Define el modelo de usuario personalizado (CustomUser), el modelo base de Cliente (Client),
el catálogo de Verticales de negocio (Vertical) con baja lógica y el libro de Transacciones
financieras (Transaction).
"""

from decimal import Decimal
import unicodedata
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (10.485.760 bytes)


def validate_pdf_size(value):
    """
    Validador estricto que rechaza cualquier archivo PDF cuyo tamaño
    supere los 10 MB (10.485.760 bytes).
    """
    if value and hasattr(value, "size") and value.size > MAX_PDF_SIZE_BYTES:
        raise ValidationError(
            "El archivo PDF supera el límite máximo permitido de 10 MB (10.485.760 bytes)."
        )


class CustomUserManager(BaseUserManager):
    """
    Gestor de usuarios personalizado donde el correo electrónico es el único
    identificador para autenticación en lugar de un nombre de usuario.
    """

    def create_user(self, email, password=None, **extra_fields):
        """Crea y guarda un usuario con el correo electrónico y contraseña dados."""
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        email = self.normalize_email(email).lower().strip()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Crea y guarda un superusuario con el correo electrónico y contraseña dados."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("El superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """
    Modelo de usuario personalizado que prescinde de `username` y utiliza
    `email` como identificador único de acceso.
    """

    username = None
    email = models.EmailField("correo electrónico", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email).lower().strip()

    def __str__(self):
        return self.email


class ClienteQuerySet(models.QuerySet):
    """QuerySet que mantiene compatibilidad entre `name` y `nombre_completo`."""

    def _translate_kwargs(self, kwargs):
        translated = {}
        for k, v in kwargs.items():
            if k == "name":
                translated["nombre_completo"] = v
            elif k.startswith("name__"):
                translated["nombre_completo__" + k[len("name__"):]] = v
            elif k == "phone":
                translated["telefono"] = v
            else:
                translated[k] = v
        return translated

    def filter(self, *args, **kwargs):
        return super().filter(*args, **self._translate_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*args, **self._translate_kwargs(kwargs))

    def create(self, **kwargs):
        return super().create(**self._translate_kwargs(kwargs))

    def order_by(self, *field_names):
        mapped = [
            "nombre_completo" if f == "name" else ("-nombre_completo" if f == "-name" else f)
            for f in field_names
        ]
        return super().order_by(*mapped)


class Cliente(models.Model):
    """
    Modelo de Cliente vinculado al usuario propietario de la cuenta.
    Incluye datos de contacto, sexo y documentación adjunta en formato PDF (máx. 10 MB).
    """

    class Sexo(models.TextChoices):
        MASCULINO = "M", "M"
        FEMENINO = "F", "F"
        OTRO = "Otro", "Otro"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clientes",
        verbose_name="usuario",
    )
    nombre_completo = models.CharField("nombre completo", max_length=150)
    email = models.EmailField("correo electrónico", blank=True, default="")
    telefono = models.CharField("teléfono", max_length=50, blank=True, default="")
    sexo = models.CharField(
        "sexo",
        max_length=10,
        choices=Sexo.choices,
        default=Sexo.OTRO,
    )
    documentacion = models.FileField(
        "documentación PDF",
        upload_to="clientes/documentacion/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf"],
                message="Formato inválido: Solo se permiten archivos con extensión .pdf.",
            ),
            validate_pdf_size,
        ],
    )
    created_at = models.DateTimeField("fecha de alta", auto_now_add=True)

    objects = ClienteQuerySet.as_manager()

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre_completo", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "nombre_completo"],
                name="unique_client_name_per_user",
            )
        ]

    def __init__(self, *args, **kwargs):
        if "name" in kwargs and "nombre_completo" not in kwargs:
            kwargs["nombre_completo"] = kwargs.pop("name")
        if "phone" in kwargs and "telefono" not in kwargs:
            kwargs["telefono"] = kwargs.pop("phone")
        super().__init__(*args, **kwargs)

    @property
    def name(self):
        return self.nombre_completo

    @name.setter
    def name(self, value):
        self.nombre_completo = value

    @property
    def phone(self):
        return self.telefono

    @phone.setter
    def phone(self, value):
        self.telefono = value

    def __str__(self):
        return self.nombre_completo


# Alias para compatibilidad con referencias existentes a Client
Client = Cliente


def normalize_vertical_title_key(value):
    """
    Normaliza un título de vertical para comparaciones de unicidad:
    convierte a minúsculas, colapsa espacios extra y elimina diacríticos/tildes.
    """
    text = " ".join(str(value or "").strip().lower().split())
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


class Vertical(models.Model):
    """
    Modelo de Vertical de negocio perteneciente a un usuario.
    Implementa baja lógica (is_active / deactivated_at) para preservar
    la integridad histórica de las transacciones asociadas.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verticals",
        verbose_name="usuario",
    )
    title = models.CharField("título", max_length=120)
    description = models.TextField("descripción", blank=True, default="")
    is_active = models.BooleanField("activa", default=True, db_index=True)
    deactivated_at = models.DateTimeField(
        "fecha de baja", null=True, blank=True
    )
    created_at = models.DateTimeField("fecha de creación", auto_now_add=True)

    class Meta:
        verbose_name = "vertical"
        verbose_name_plural = "verticales"
        ordering = ["title", "-id"]
        constraints = [
            models.UniqueConstraint(
                Lower("title"),
                "user",
                condition=Q(is_active=True),
                name="unique_active_vertical_title_per_user",
            )
        ]

    def clean(self):
        super().clean()
        self.title = " ".join((self.title or "").strip().split())
        self.description = (self.description or "").strip()
        if not self.title:
            raise ValidationError(
                {"title": "El título de la vertical es obligatorio."}
            )

        if self.is_active and self.user_id:
            target_key = normalize_vertical_title_key(self.title)
            active_qs = Vertical.objects.filter(
                user_id=self.user_id, is_active=True
            )
            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)
            for existing in active_qs:
                if (
                    existing.title.strip().lower() == self.title.lower()
                    or normalize_vertical_title_key(existing.title)
                    == target_key
                ):
                    raise ValidationError(
                        {
                            "title": "Ya existe una vertical activa con este título."
                        }
                    )

    def save(self, *args, **kwargs):
        self.title = " ".join((self.title or "").strip().split())
        self.description = (self.description or "").strip()
        super().save(*args, **kwargs)

    def deactivate(self):
        """Realiza la baja lógica de la vertical sin eliminarla físicamente."""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at"])

    def __str__(self):
        if not self.is_active:
            return f"{self.title} (Inactiva)"
        return self.title


class Transaction(models.Model):
    """
    Registro contable de flujo de caja (Ingreso o Gasto) perteneciente a un usuario.
    Estructura contable de 8 campos operativos:
    Fecha, Vertical (FK PROTECT), Tipo, Concepto, Cliente (FK), Detalle, Monto y Moneda (ARS/USD).
    """

    class TransactionType(models.TextChoices):
        INCOME = "INGRESO", "Ingreso"
        EXPENSE = "GASTO", "Gasto"

    class Currency(models.TextChoices):
        ARS = "ARS", "ARS"
        USD = "USD", "USD"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="usuario",
    )
    date = models.DateField("fecha", db_index=True)
    vertical = models.ForeignKey(
        Vertical,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="vertical",
    )
    transaction_type = models.CharField(
        "tipo",
        max_length=10,
        choices=TransactionType.choices,
        default=TransactionType.INCOME,
        db_index=True,
    )
    concept = models.CharField("concepto", max_length=150)
    client = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name="cliente",
    )
    detail = models.CharField("detalle", max_length=255, blank=True, default="")
    amount = models.DecimalField(
        "monto",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(
        "moneda",
        max_length=3,
        choices=Currency.choices,
        default=Currency.ARS,
        db_index=True,
    )
    created_at = models.DateTimeField("fecha de creación", auto_now_add=True)
    updated_at = models.DateTimeField("última actualización", auto_now=True)

    class Meta:
        verbose_name = "transacción"
        verbose_name_plural = "transacciones"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "-date"], name="idx_tx_user_date"),
            models.Index(
                fields=["user", "transaction_type"], name="idx_tx_user_type"
            ),
            models.Index(
                fields=["user", "currency"], name="idx_tx_user_currency"
            ),
        ]

    def __init__(self, *args, **kwargs):
        raw_vertical = kwargs.get("vertical", None)
        if isinstance(raw_vertical, str):
            raw_str = raw_vertical.strip()
            if not raw_str:
                kwargs["vertical"] = None
            else:
                user_obj = kwargs.get("user")
                user_id = kwargs.get("user_id") or getattr(user_obj, "id", None)
                if user_id:
                    vert = Vertical.objects.filter(
                        user_id=user_id, title__iexact=raw_str
                    ).order_by("-is_active", "-id").first()
                    if vert is None:
                        vert = Vertical.objects.create(
                            user_id=user_id, title=raw_str, is_active=True
                        )
                    kwargs["vertical"] = vert
                else:
                    kwargs["vertical"] = None
        super().__init__(*args, **kwargs)

    @property
    def vertical_title(self):
        return self.vertical.title if self.vertical_id and self.vertical else ""

    def clean(self):
        super().clean()
        if self.vertical_id is not None and self.vertical is not None:
            if self.user_id and self.vertical.user_id != self.user_id:
                raise ValidationError(
                    {
                        "vertical": "La vertical seleccionada no pertenece a su cuenta."
                    }
                )
            if not self.vertical.is_active:
                allow_historical = False
                if self.pk:
                    original_vertical_id = (
                        Transaction.objects.filter(pk=self.pk)
                        .values_list("vertical_id", flat=True)
                        .first()
                    )
                    if original_vertical_id == self.vertical_id:
                        allow_historical = True
                if not allow_historical:
                    raise ValidationError(
                        {
                            "vertical": "No se puede asignar una vertical dada de baja (inactiva) a la transacción."
                        }
                    )

    def save(self, *args, **kwargs):
        if self.transaction_type == "EGRESO":
            self.transaction_type = self.TransactionType.EXPENSE
        if self.user_id is None and self.client_id is not None:
            self.user_id = self.client.user_id
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.date} | {self.get_transaction_type_display()} | "
            f"{self.currency} {self.amount} — {self.concept}"
        )
