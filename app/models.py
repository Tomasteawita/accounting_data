"""
Modelos de datos para la aplicación app.
Define el modelo de usuario personalizado basado exclusivamente en correo electrónico.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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
