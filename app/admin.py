"""
Configuración del panel de administración para la aplicación app.
Adapta UserAdmin al modelo CustomUser sin el campo username.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import Cliente, CustomUser, Transaction


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Administración de CustomUser basada exclusivamente en correo electrónico."""

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser

    list_display = ("email", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información personal", {"fields": ("first_name", "last_name")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas importantes", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "user", "email", "telefono", "sexo", "documentacion", "created_at")
    search_fields = ("nombre_completo", "email", "user__email")
    list_filter = ("sexo", "created_at")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "vertical",
        "transaction_type",
        "concept",
        "client",
        "detail",
        "amount",
        "currency",
        "user",
    )
    list_filter = ("transaction_type", "currency", "vertical", "date")
    search_fields = ("concept", "detail", "vertical", "client__nombre_completo", "user__email")
    ordering = ("-date", "-id")
