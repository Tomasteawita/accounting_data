"""
Modelos de datos para la aplicación app.
Define el modelo de usuario personalizado (CustomUser), el modelo base de Cliente (Client)
y el libro de Transacciones financieras (Transaction).
"""

from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

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


class Transaction(models.Model):
    """
    Registro contable de flujo de caja (Ingreso o Gasto) perteneciente a un usuario.
    Estructura contable de 8 campos operativos:
    Fecha, Vertical, Tipo, Concepto, Cliente (FK), Detalle, Monto y Moneda (ARS/USD).
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
    vertical = models.CharField(
        "vertical", max_length=120, blank=True, default="", db_index=True
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
