"""
Suite de pruebas unitarias y de integración para la aplicación app.
Cubre la Landing Page, el modelo CustomUser y los flujos completos de autenticación.
"""

from decimal import Decimal
import io
import json

import pandas as pd
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Client, Cliente, Transaction, Vertical

CustomUser = get_user_model()


class LandingPageTests(SimpleTestCase):
    """Pruebas de integración para la Landing Page sin consultas a PostgreSQL."""

    def test_home_page_status_and_templates(self):
        response = self.client.get(reverse("app:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/home.html")
        self.assertTemplateUsed(response, "app/base.html")

    def test_home_page_exact_content(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        # Header para usuario anónimo
        self.assertContains(response, "Tomas Cueva")
        self.assertContains(response, "Iniciar Sesión")
        self.assertContains(response, "Registrarse")

        # Sección 1: Hero <h1> exacto
        self.assertContains(
            response,
            '<h1 class="hero-title">Gastarte toda la plata de tu negocio en comprar materiales y maquinas para <u class="hero-underline">"atender a más clientes"</u> es la principal razón por la cual te vas a fundir.</h1>',
            html=True,
        )

        # Sección 2: Diagnóstico de Síntomas
        self.assertContains(
            response,
            'Si te gastas la plata en tu negocio para """poner la plata en movimiento""" pero te están pasando estas tres cosas:',
        )
        self.assertContains(
            response,
            "<strong>no vez reflejado el crecimiento en tu cuenta bancaria</strong>",
        )
        self.assertContains(
            response,
            "<strong>pagar todo en cuotas o con un prestamo</strong>",
        )
        self.assertContains(
            response,
            "<strong>endeudarte</strong>",
        )
        self.assertContains(
            response,
            "Estás perdiendo plata de a poco y no te estás dando cuenta.",
        )

        # Sección 3: El Sistema
        self.assertContains(response, '[ EL SISTEMA: "EL AHORRO ES PRIMERO" ]')
        self.assertContains(response, "Por eso diseñe un sistema financiero para:")
        self.assertContains(
            response,
            "<strong>ganes más plata con la misma cantidad de ventas</strong>",
        )
        self.assertContains(
            response,
            "<strong>Ahorres todos los meses</strong>",
        )
        self.assertContains(
            response,
            "<strong>cuanto es lo mínimo que necesitas vender para cubrir todos los gastos de tu negocio</strong>",
        )

        # Sección 4: Casos de exito e iframe YouTube
        self.assertContains(response, "Casos de exito")
        self.assertContains(response, "4h_RZRdgGh4")
        self.assertContains(
            response,
            "https://www.youtube-nocookie.com/embed/4h_RZRdgGh4",
        )

        # Sección 5: CTA y enlace de WhatsApp
        self.assertContains(response, "Registrarme")
        self.assertContains(response, "https://wa.me/5491123966199")
        self.assertContains(response, "11 2396-6199")


class CustomUserModelTests(TestCase):
    """1. Pruebas para la creación de CustomUser exclusivamente con email y contraseña."""

    def test_create_user_with_email_only(self):
        user = CustomUser.objects.create_user(
            email="  ADMIN@Empresa.com ", password="PasswordSegura123!"
        )
        self.assertEqual(user.email, "admin@empresa.com")
        self.assertTrue(user.check_password("PasswordSegura123!"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.username)
        self.assertEqual(str(user), "admin@empresa.com")

    def test_create_user_without_email_raises_error(self):
        with self.assertRaises(ValueError):
            CustomUser.objects.create_user(email="", password="PasswordSegura123!")

    def test_create_superuser(self):
        admin_user = CustomUser.objects.create_superuser(
            email="root@empresa.com", password="PasswordSegura123!"
        )
        self.assertEqual(admin_user.email, "root@empresa.com")
        self.assertTrue(admin_user.is_active)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)


class RegistrationAndActivationTests(TestCase):
    """
    2. Registro de usuario (is_active=False) y despacho del correo de activación.
    3. Activación de cuenta con token válido e intento fallido con token inválido.
    """

    def setUp(self):
        cache.clear()
        mail.outbox = []

    def test_register_creates_inactive_user_and_sends_activation_email(self):
        response = self.client.post(
            reverse("app:register"),
            {
                "email": "  NuevoUsuario@Empresa.com  ",
                "password1": "ContrasenaFuerte2026!",
                "password2": "ContrasenaFuerte2026!",
            },
        )
        self.assertRedirects(response, reverse("app:verify_email_sent"))

        user = CustomUser.objects.get(email="nuevousuario@empresa.com")
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("nuevousuario@empresa.com", mail.outbox[0].to)
        self.assertIn("/auth/verify-email/", mail.outbox[0].body)

    def test_activate_account_with_valid_token(self):
        user = CustomUser.objects.create_user(
            email="pendiente@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=False,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        url = reverse(
            "app:activate_account", kwargs={"uidb64": uidb64, "token": token}
        )
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse("app:login"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertContains(
            response, "Cuenta activada correctamente. Ya puede iniciar sesión."
        )

    def test_activate_account_with_invalid_token_fails(self):
        user = CustomUser.objects.create_user(
            email="invalido@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=False,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        url = reverse(
            "app:activate_account",
            kwargs={"uidb64": uidb64, "token": "token-invalido-000"},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "app/auth/verify_email_invalid.html")
        self.assertContains(response, reverse("app:resend_activation"), status_code=400)
        user.refresh_from_db()
        self.assertFalse(user.is_active)


class LoginAndLogoutFlowTests(TestCase):
    """
    4. Bloqueo de login cuando is_active=False mostrando el mensaje de cuenta inactiva,
       y login exitoso tras activar la cuenta.
    """

    def setUp(self):
        self.email = "cliente@empresa.com"
        self.password = "ContrasenaFuerte2026!"
        self.user = CustomUser.objects.create_user(
            email=self.email,
            password=self.password,
            is_active=False,
        )

    def test_login_blocked_for_inactive_user_shows_inactive_message_and_resend_link(
        self,
    ):
        response = self.client.post(
            reverse("app:login"),
            {"username": self.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Su cuenta aún no ha sido activada")
        self.assertContains(response, reverse("app:resend_activation"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_succeeds_after_activation_and_logout_via_post_only(self):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("app:login"),
            {"username": "  CLIENTE@Empresa.com ", "password": self.password},
            follow=True,
        )
        self.assertRedirects(response, reverse("app:dashboard"))
        self.assertContains(response, self.email)
        self.assertContains(response, "Cerrar Sesión")

        # GET a logout debe ser rechazado (405 Method Not Allowed)
        get_logout = self.client.get(reverse("app:logout"))
        self.assertEqual(get_logout.status_code, 405)

        # POST a logout cierra la sesión y redirige a login
        post_logout = self.client.post(reverse("app:logout"))
        self.assertRedirects(post_logout, reverse("app:login"))


class ResendActivationTests(TestCase):
    """
    5. Endpoint de reenvío de activación (resend_activation):
       - Envío correcto para cuentas inactivas.
       - Bloqueo por rate-limit (cooldown de 120s en caché) en intentos consecutivos.
       - No envío para cuentas ya activas.
    """

    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.inactive_user = CustomUser.objects.create_user(
            email="inactivo@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=False,
        )
        self.active_user = CustomUser.objects.create_user(
            email="activo@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )

    def test_resend_activation_get_prefills_email_from_query_param(self):
        response = self.client.get(
            f"{reverse('app:resend_activation')}?email=inactivo@empresa.com"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="inactivo@empresa.com"')

    def test_resend_activation_sends_email_and_enforces_120s_cooldown(self):
        # Primer intento: despacha correo y guarda clave en caché
        response1 = self.client.post(
            reverse("app:resend_activation"),
            {"email": "  INACTIVO@Empresa.com "},
        )
        self.assertRedirects(response1, reverse("app:verify_email_sent"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(cache.get("resend_cooldown_inactivo@empresa.com"))

        # Segundo intento inmediato: bloqueado por rate-limit (cooldown 120s)
        response2 = self.client.post(
            reverse("app:resend_activation"),
            {"email": "inactivo@empresa.com"},
        )
        self.assertEqual(response2.status_code, 200)
        self.assertContains(
            response2,
            "Debe aguardar 2 minutos antes de solicitar otro enlace de activación.",
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_activation_does_not_send_email_for_active_or_nonexistent_users(
        self,
    ):
        # Cuenta ya activa
        response_active = self.client.post(
            reverse("app:resend_activation"),
            {"email": "activo@empresa.com"},
        )
        self.assertRedirects(response_active, reverse("app:verify_email_sent"))
        self.assertEqual(len(mail.outbox), 0)

        # Cuenta inexistente (anti-enumeración: redirige igual sin enviar correo)
        response_missing = self.client.post(
            reverse("app:resend_activation"),
            {"email": "noexiste@empresa.com"},
        )
        self.assertRedirects(response_missing, reverse("app:verify_email_sent"))
        self.assertEqual(len(mail.outbox), 0)


class PasswordResetFlowTests(TestCase):
    """
    6. Flujo completo de recuperación de contraseña (password_reset -> password_reset_confirm).
    """

    def setUp(self):
        mail.outbox = []
        self.email = "recuperar@empresa.com"
        self.old_password = "PasswordAntigua123!"
        self.new_password = "PasswordNueva456!"
        self.user = CustomUser.objects.create_user(
            email=self.email,
            password=self.old_password,
            is_active=True,
        )

    def test_complete_password_reset_flow(self):
        # Paso 1: Solicitar recuperación de contraseña
        response_reset = self.client.post(
            reverse("app:password_reset"),
            {"email": "  RECUPERAR@empresa.com "},
        )
        self.assertRedirects(response_reset, reverse("app:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.email, mail.outbox[0].to)

        # Paso 2: Generar uid y token para el enlace de confirmación
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse(
            "app:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )
        self.assertIn(confirm_url, mail.outbox[0].body)

        # Paso 3: Seguir el enlace inicial (que redirige a set-password en sesión)
        response_get_confirm = self.client.get(confirm_url, follow=True)
        self.assertEqual(response_get_confirm.status_code, 200)
        set_password_url = response_get_confirm.redirect_chain[-1][0]

        # Paso 4: Enviar la nueva contraseña
        response_post_confirm = self.client.post(
            set_password_url,
            {
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
            follow=True,
        )
        self.assertRedirects(
            response_post_confirm, reverse("app:password_reset_complete")
        )

        # Verificar que la contraseña se actualizó en la base de datos
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))


class DashboardAndNavigationTests(TestCase):
    """
    7. Pruebas para el módulo Dashboard y la navegación por las interfaces de la App
       (Inicio / Dashboard, Clientes, Transacciones, Métricas).
    """

    def setUp(self):
        self.email = "operador@empresa.com"
        self.password = "ContrasenaFuerte2026!"
        self.user = CustomUser.objects.create_user(
            email=self.email,
            password=self.password,
            is_active=True,
        )
        self.app_routes = [
            ("app:dashboard", "app/dashboard.html", "Inicio"),
            ("app:clients", "app/clientes.html", "Clientes"),
            ("app:verticals", "app/verticals.html", "Verticales"),
            ("app:transactions", "app/transactions.html", "Transacciones"),
            ("app:metrics", "app/metrics.html", "Métricas"),
        ]

    def test_anonymous_users_are_redirected_to_login(self):
        for route_name, _, _ in self.app_routes:
            url = reverse(route_name)
            response = self.client.get(url)
            self.assertRedirects(
                response, f"{reverse('app:login')}?next={url}"
            )

    def test_authenticated_user_automatically_enters_dashboard_from_public_entrypoints(
        self,
    ):
        self.client.force_login(self.user)

        # Acceso a la raíz '/' con sesión activa redirige al Dashboard
        response_home = self.client.get(reverse("app:home"))
        self.assertRedirects(response_home, reverse("app:dashboard"))

        # Acceso a '/auth/login/' con sesión activa redirige al Dashboard
        response_login = self.client.get(reverse("app:login"))
        self.assertRedirects(response_login, reverse("app:dashboard"))

        # Acceso a '/auth/register/' con sesión activa redirige al Dashboard
        response_register = self.client.get(reverse("app:register"))
        self.assertRedirects(response_register, reverse("app:dashboard"))

    def test_authenticated_navigation_and_blank_interfaces(self):
        self.client.force_login(self.user)

        for route_name, expected_template, label in self.app_routes:
            url = reverse(route_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "app/app_base.html")
            self.assertTemplateUsed(response, expected_template)

            # Verificar presencia de los 5 ítems del menú y controles del drawer/sidebar
            self.assertContains(response, 'id="app-sidebar"')
            self.assertContains(response, 'id="sidebar-toggle"')
            self.assertContains(response, 'id="sidebar-close"')
            self.assertContains(response, 'id="sidebar-backdrop"')
            self.assertContains(response, reverse("app:dashboard"))
            self.assertContains(response, reverse("app:clients"))
            self.assertContains(response, reverse("app:verticals"))
            self.assertContains(response, reverse("app:transactions"))
            self.assertContains(response, reverse("app:metrics"))
            self.assertContains(response, "Inicio")
            self.assertContains(response, "Clientes")
            self.assertContains(response, "Verticales")
            self.assertContains(response, "Transacciones")
            self.assertContains(response, "Métricas")

            # Verificar que el ítem activo corresponde a la interfaz actual
            self.assertContains(response, 'aria-current="page"', count=1)
            self.assertContains(response, "app-nav-link--active", count=1)
            if route_name == "app:dashboard":
                self.assertContains(response, 'id="pnl-table"')
            elif route_name == "app:transactions":
                self.assertContains(response, 'id="transactions-table"')
            elif route_name == "app:clients":
                self.assertContains(response, 'id="clients-table"')
            elif route_name == "app:verticals":
                self.assertContains(response, 'id="verticals-table"')
            else:
                self.assertContains(
                    response,
                    f'<section class="blank-workspace" aria-label="{label}"></section>',
                    html=True,
                )


class TransactionModuleTests(TestCase):
    """
    8. Pruebas integrales para el módulo de Transacciones:
       - Creación individual, modificación, guardado en lote ("Guardar Cambios") y eliminación.
       - Ingesta masiva en memoria (CSV) mediante pandas sin persistencia en disco.
       - Aislamiento estricto entre usuarios.
    """

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="finanzas@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.other_user = CustomUser.objects.create_user(
            email="otro@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.client_obj = Client.objects.create(
            user=self.user, name="Corporación Austral"
        )
        self.v_consultoria_fin = Vertical.objects.create(
            user=self.user, title="Consultoría Financiera", is_active=True
        )
        self.v_balanz = Vertical.objects.create(
            user=self.user, title="Inversiones Balanz", is_active=True
        )
        self.v_operaciones = Vertical.objects.create(
            user=self.user, title="Operaciones", is_active=True
        )
        self.v_consultoria = Vertical.objects.create(
            user=self.user, title="Consultoría", is_active=True
        )
        self.v_infra = Vertical.objects.create(
            user=self.user, title="Infraestructura", is_active=True
        )
        self.url = reverse("app:transactions")

    def test_create_update_bulk_save_and_delete_transactions_via_json(self):
        self.client.force_login(self.user)

        # 1. Crear transacción individual pasando el nombre de un cliente nuevo
        res_create = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "action": "create",
                    "date": "2026-11-09",
                    "vertical": "Consultoría Financiera",
                    "transaction_type": "INGRESO",
                    "concept": "Honorarios Mensuales",
                    "client": "Grupo Pampa S.A.",
                    "detail": "Abono noviembre Profit First",
                    "amount": "150000.50",
                    "currency": "ARS",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_create.status_code, 201)
        data_create = res_create.json()
        self.assertEqual(data_create["status"], "ok")
        tx_id = data_create["transaction"]["id"]
        created_client = Client.objects.get(user=self.user, name="Grupo Pampa S.A.")
        self.assertEqual(data_create["transaction"]["client"], created_client.id)
        self.assertEqual(data_create["transaction"]["vertical"], "Consultoría Financiera")
        self.assertEqual(data_create["transaction"]["detail"], "Abono noviembre Profit First")
        self.assertEqual(data_create["transaction"]["currency"], "ARS")

        # 2. Modificar transacción individual (cambiando a USD y cliente existente por ID)
        res_update = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "action": "update",
                    "id": tx_id,
                    "date": "2026-11-09",
                    "vertical": "Inversiones Balanz",
                    "transaction_type": "INGRESO",
                    "concept": "Honorarios Estructuración",
                    "client": self.client_obj.id,
                    "detail": "Cartera dolarizada",
                    "amount": "1200.00",
                    "currency": "USD",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_update.status_code, 200)
        updated_tx = Transaction.objects.get(pk=tx_id)
        self.assertEqual(Decimal(updated_tx.amount), Decimal("1200.00"))
        self.assertEqual(updated_tx.currency, "USD")
        self.assertEqual(updated_tx.client_id, self.client_obj.id)

        # 3. Guardar Cambios en lote (bulk_save: actualiza existente + crea nueva fila de Gasto)
        res_bulk = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "action": "bulk_save",
                    "rows": [
                        {
                            "id": tx_id,
                            "date": "2026-11-09",
                            "vertical": "Inversiones Balanz",
                            "transaction_type": "INGRESO",
                            "concept": "Honorarios Estructuración",
                            "client": "Corporación Austral",
                            "detail": "Confirmado en cuenta",
                            "amount": "1250.00",
                            "currency": "USD",
                        },
                        {
                            "id": None,
                            "date": "2026-11-09",
                            "vertical": "Operaciones",
                            "transaction_type": "GASTO",
                            "concept": "Licencias Software",
                            "client": "",
                            "detail": "Servidor AWS EC2",
                            "amount": "42500.75",
                            "currency": "ARS",
                        },
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_bulk.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

        # 4. Eliminar transacción
        res_delete = self.client.post(
            self.url,
            data=json.dumps({"action": "delete", "id": tx_id}),
            content_type="application/json",
        )
        self.assertEqual(res_delete.status_code, 200)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_in_memory_csv_upload_with_pandas_8_columns(self):
        self.client.force_login(self.user)
        csv_content = (
            "Fecha,Vertical,Tipo,Concepto,Cliente,Detalle,Monto,Moneda\n"
            "2026-11-01,Consultoría,Ingreso,Abono Mensual,Cliente Norte,Cuota 1 de 6,\"$ 250.000,50\",ARS\n"
            "2026-11-02,Infraestructura,Gasto,Servidores,,Instancia t4g.small,15.00,USD\n"
        ).encode("utf-8")
        uploaded = SimpleUploadedFile(
            "flujo_noviembre.csv", csv_content, content_type="text/csv"
        )

        response = self.client.post(
            self.url,
            {"action": "bulk_upload", "file": uploaded},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["imported_count"], 2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

        norte_client = Client.objects.get(user=self.user, name="Cliente Norte")
        tx_ingreso = Transaction.objects.get(
            user=self.user, transaction_type="INGRESO"
        )
        self.assertEqual(tx_ingreso.client_id, norte_client.id)
        self.assertEqual(tx_ingreso.vertical_id, self.v_consultoria.id)
        self.assertEqual(tx_ingreso.vertical.title, "Consultoría")
        self.assertEqual(tx_ingreso.detail, "Cuota 1 de 6")
        self.assertEqual(tx_ingreso.currency, "ARS")

        tx_gasto = Transaction.objects.get(user=self.user, transaction_type="GASTO")
        self.assertIsNone(tx_gasto.client_id)
        self.assertEqual(tx_gasto.currency, "USD")
        self.assertEqual(tx_gasto.amount, Decimal("15.00"))

    def test_pagination_default_25_and_max_100_cap(self):
        self.client.force_login(self.user)
        Transaction.objects.bulk_create(
            [
                Transaction(
                    user=self.user,
                    date="2026-11-01",
                    vertical="Operaciones",
                    transaction_type="INGRESO",
                    concept=f"Operación #{i}",
                    amount=Decimal("100.00"),
                    currency="ARS",
                )
                for i in range(1, 121)
            ]
        )

        # Por defecto muestra 25 filas (total 120 -> 5 páginas)
        res_default = self.client.get(
            self.url, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(res_default.status_code, 200)
        data_default = res_default.json()
        self.assertEqual(len(data_default["transactions"]), 25)
        self.assertEqual(data_default["pagination"]["per_page"], 25)
        self.assertEqual(data_default["pagination"]["total_count"], 120)
        self.assertEqual(data_default["pagination"]["total_pages"], 5)

        # Solicitar per_page=500 se limita estrictamente a 100 filas
        res_capped = self.client.get(
            f"{self.url}?page=1&per_page=500",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_capped.status_code, 200)
        data_capped = res_capped.json()
        self.assertEqual(len(data_capped["transactions"]), 100)
        self.assertEqual(data_capped["pagination"]["per_page"], 100)
        self.assertEqual(data_capped["pagination"]["total_pages"], 2)

    def test_download_template_xlsx_and_reimport_roundtrip(self):
        """
        Verifica que 'Descargar Plantilla' devuelve un archivo .xlsx válido con las 8 cabeceras
        esperadas y que sus filas guía pueden reimportarse directamente mediante bulk_upload.
        """
        self.client.force_login(self.user)
        template_url = reverse("app:transactions_template")

        response = self.client.get(template_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            'attachment; filename="plantilla_transacciones.xlsx"',
            response["Content-Disposition"],
        )

        # Inspeccionar estructura de columnas en memoria con pandas
        df = pd.read_excel(io.BytesIO(response.content), dtype=str, keep_default_na=False)
        expected_columns = [
            "Fecha",
            "Vertical",
            "Tipo",
            "Concepto",
            "Cliente",
            "Detalle",
            "Monto",
            "Moneda",
        ]
        self.assertEqual(list(df.columns), expected_columns)
        self.assertEqual(len(df), 2)

        # Round-trip: subir la plantilla descargada directamente a bulk_upload
        uploaded_template = SimpleUploadedFile(
            "plantilla_transacciones.xlsx",
            response.content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        res_import = self.client.post(
            self.url,
            {"action": "bulk_upload", "file": uploaded_template},
        )
        self.assertEqual(res_import.status_code, 200)
        payload = res_import.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["imported_count"], 2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

    def test_export_transactions_by_date_range_user_isolation_and_roundtrip(self):
        """
        Verifica la exportación de transacciones en un rango [fecha_desde, fecha_hasta],
        el aislamiento respecto a otros usuarios y la compatibilidad round-trip con Importar Archivo.
        """
        self.client.force_login(self.user)
        export_url = reverse("app:transactions_export")

        # Crear transacciones dentro y fuera del rango para self.user, y una para other_user
        Transaction.objects.bulk_create(
            [
                Transaction(
                    user=self.user,
                    date="2026-10-31",
                    vertical="Fuera Rango",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Octubre",
                    amount=Decimal("500.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-11-05",
                    vertical="Consultoría",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Abono Noviembre",
                    client=self.client_obj,
                    detail="Factura A-001",
                    amount=Decimal("185000.50"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-11-15",
                    vertical="Infraestructura",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Servidor Cloud",
                    client=None,
                    detail="Instancia EC2",
                    amount=Decimal("42.75"),
                    currency=Transaction.Currency.USD,
                ),
                Transaction(
                    user=self.user,
                    date="2026-12-01",
                    vertical="Fuera Rango",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Diciembre",
                    amount=Decimal("900.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.other_user,
                    date="2026-11-10",
                    vertical="Ajena",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="No Debe Exportarse",
                    amount=Decimal("999999.00"),
                    currency=Transaction.Currency.ARS,
                ),
            ]
        )

        response = self.client.get(
            f"{export_url}?fecha_desde=2026-11-01&fecha_hasta=2026-11-30"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            'attachment; filename="transacciones_2026-11-01_a_2026-11-30.xlsx"',
            response["Content-Disposition"],
        )

        df = pd.read_excel(io.BytesIO(response.content), dtype=str, keep_default_na=False)
        self.assertEqual(
            list(df.columns),
            ["Fecha", "Vertical", "Tipo", "Concepto", "Cliente", "Detalle", "Monto", "Moneda"],
        )
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["Fecha"], "2026-11-05")
        self.assertEqual(df.iloc[0]["Tipo"], "Ingreso")
        self.assertEqual(df.iloc[0]["Concepto"], "Abono Noviembre")
        self.assertEqual(df.iloc[0]["Cliente"], "Corporación Austral")
        self.assertEqual(df.iloc[0]["Monto"], "185000.50")
        self.assertEqual(df.iloc[0]["Moneda"], "ARS")

        self.assertEqual(df.iloc[1]["Fecha"], "2026-11-15")
        self.assertEqual(df.iloc[1]["Tipo"], "Gasto")
        self.assertEqual(df.iloc[1]["Concepto"], "Servidor Cloud")
        self.assertEqual(df.iloc[1]["Cliente"], "")
        self.assertEqual(df.iloc[1]["Monto"], "42.75")
        self.assertEqual(df.iloc[1]["Moneda"], "USD")

        # Round-trip: limpiar transacciones del usuario y reimportar el Excel exportado
        Transaction.objects.filter(user=self.user).delete()
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        exported_file = SimpleUploadedFile(
            "transacciones_2026-11-01_a_2026-11-30.xlsx",
            response.content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        res_reimport = self.client.post(
            self.url,
            {"action": "bulk_upload", "file": exported_file},
        )
        self.assertEqual(res_reimport.status_code, 200)
        self.assertEqual(res_reimport.json()["imported_count"], 2)

        reimported = list(
            Transaction.objects.filter(user=self.user).order_by("date", "id")
        )
        self.assertEqual(len(reimported), 2)
        self.assertEqual(reimported[0].concept, "Abono Noviembre")
        self.assertEqual(reimported[0].client_id, self.client_obj.id)
        self.assertEqual(reimported[0].amount, Decimal("185000.50"))
        self.assertEqual(reimported[1].concept, "Servidor Cloud")
        self.assertEqual(reimported[1].transaction_type, Transaction.TransactionType.EXPENSE)
        self.assertEqual(reimported[1].amount, Decimal("42.75"))
        self.assertEqual(reimported[1].currency, Transaction.Currency.USD)

    def test_export_transactions_validation_and_empty_range_edge_cases(self):
        """
        Verifica los casos borde de exportación:
        - Fechas faltantes o con formato inválido (400).
        - Rango invertido fecha_desde > fecha_hasta (400).
        - Rango válido sin transacciones registradas (404).
        """
        self.client.force_login(self.user)
        export_url = reverse("app:transactions_export")

        # 1. Fechas faltantes
        res_missing = self.client.get(
            export_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(res_missing.status_code, 400)
        self.assertEqual(res_missing.json()["status"], "error")

        # 2. Formato de fecha inválido
        res_invalid = self.client.get(
            f"{export_url}?fecha_desde=fecha-invalida&fecha_hasta=2026-11-30",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_invalid.status_code, 400)
        self.assertIn("Formato de fecha inválido", res_invalid.json()["message"])

        # 3. Rango invertido (fecha_desde > fecha_hasta)
        res_inverted = self.client.get(
            f"{export_url}?fecha_desde=2026-11-30&fecha_hasta=2026-11-01",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_inverted.status_code, 400)
        self.assertIn("no puede ser posterior", res_inverted.json()["message"])

        # 4. Sin transacciones en el rango
        res_empty = self.client.get(
            f"{export_url}?fecha_desde=2025-01-01&fecha_hasta=2025-01-31",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_empty.status_code, 404)
        self.assertIn("No se encontraron transacciones", res_empty.json()["message"])


class ClienteModuleTests(TestCase):
    """
    9. Pruebas integrales para el módulo de Clientes:
       - Creación, edición y eliminación de clientes.
       - Validación estricta de documentación PDF (extensión .pdf y peso máx. 10 MB / 10.485.760 bytes).
    """

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="cartera@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.url = reverse("app:clients")

    def test_create_edit_and_delete_cliente_with_valid_pdf(self):
        self.client.force_login(self.user)
        valid_pdf = SimpleUploadedFile(
            "legajo_cliente.pdf",
            b"%PDF-1.4 contenido de prueba",
            content_type="application/pdf",
        )

        # 1. Crear cliente con PDF válido
        res_create = self.client.post(
            self.url,
            {
                "action": "create",
                "nombre_completo": "Martín Echeverría",
                "email": "Martin@Empresa.com",
                "telefono": "+54 9 11 4455-6677",
                "sexo": "M",
                "documentacion": valid_pdf,
            },
        )
        self.assertEqual(res_create.status_code, 201)
        payload = res_create.json()
        self.assertEqual(payload["status"], "ok")
        client_id = payload["cliente"]["id"]
        self.assertTrue(payload["cliente"]["has_pdf"])

        cliente_db = Cliente.objects.get(pk=client_id)
        self.assertEqual(cliente_db.nombre_completo, "Martín Echeverría")
        self.assertEqual(cliente_db.email, "martin@empresa.com")
        self.assertEqual(cliente_db.sexo, "M")

        # 2. Editar cliente
        res_update = self.client.post(
            self.url,
            {
                "action": "update",
                "id": client_id,
                "nombre_completo": "Martín Echeverría S.R.L.",
                "email": "contacto@echeverria.com",
                "telefono": "11 9988-7766",
                "sexo": "Otro",
            },
        )
        self.assertEqual(res_update.status_code, 200)
        cliente_db.refresh_from_db()
        self.assertEqual(cliente_db.nombre_completo, "Martín Echeverría S.R.L.")
        self.assertEqual(cliente_db.sexo, "Otro")

        # 3. Eliminar cliente
        res_delete = self.client.post(
            self.url,
            data=json.dumps({"action": "delete", "id": client_id}),
            content_type="application/json",
        )
        self.assertEqual(res_delete.status_code, 200)
        self.assertFalse(Cliente.objects.filter(pk=client_id).exists())

    def test_reject_pdf_exceeding_10mb_and_non_pdf_extension(self):
        self.client.force_login(self.user)

        # 1. Rechazar archivo con extensión distinta de .pdf
        invalid_ext = SimpleUploadedFile(
            "documento.txt",
            b"texto plano no permitido",
            content_type="text/plain",
        )
        res_ext = self.client.post(
            self.url,
            {
                "action": "create",
                "nombre_completo": "Cliente Formato Inválido",
                "sexo": "F",
                "documentacion": invalid_ext,
            },
        )
        self.assertEqual(res_ext.status_code, 400)
        self.assertIn(".pdf", res_ext.json()["message"])

        # 2. Rechazar PDF que supere 10 MB (10.485.760 bytes)
        oversized_pdf = SimpleUploadedFile(
            "pesado.pdf",
            b"%PDF-1.4 " + (b"0" * 10485760),
            content_type="application/pdf",
        )
        res_size = self.client.post(
            self.url,
            {
                "action": "create",
                "nombre_completo": "Cliente PDF Excedido",
                "sexo": "M",
                "documentacion": oversized_pdf,
            },
        )
        self.assertEqual(res_size.status_code, 400)
        self.assertIn("10 MB", res_size.json()["message"])
        self.assertFalse(
            Cliente.objects.filter(nombre_completo="Cliente PDF Excedido").exists()
        )


class PnLDashboardTests(TestCase):
    """
    10. Pruebas unitarias y de integración para el Estado de Resultados (P&L Mensual)
        en `dashboard_view`:
        - Cálculo exacto de Ingresos, OPEX, EBITDA, Margen EBITDA %, CAPEX/Deuda y
          Resultado Neto de Caja (Flujo Libre) con `decimal.Decimal`.
        - Clasificación contable de `Estructura` y `Deuda` como No Operativos y ordenamiento
          descendente por monto anual acumulado.
        - Manejo seguro de meses con Ingresos = 0 (`0.0%` sin `ZeroDivisionError`).
        - Filtros por Año, Moneda (`ARS`/`USD`), Vertical y aislamiento entre usuarios.
    """

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="cfo@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.other_user = CustomUser.objects.create_user(
            email="externo@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.url = reverse("app:dashboard")

        # Transacciones de Enero 2026 (ARS, Vertical Academia)
        Transaction.objects.bulk_create(
            [
                Transaction(
                    user=self.user,
                    date="2026-01-10",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Cuota Alumnos",
                    amount=Decimal("1000000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-01-15",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Otros Ingresos",
                    amount=Decimal("200000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-01-20",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Sueldo",
                    amount=Decimal("400000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-01-22",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Alquiler",
                    amount=Decimal("200000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-01-25",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Luz",
                    amount=Decimal("60000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                # Gastos No Operativos (CAPEX y Servicio de Deuda) con variantes de mayúsculas
                Transaction(
                    user=self.user,
                    date="2026-01-28",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Estructura",
                    amount=Decimal("100000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                Transaction(
                    user=self.user,
                    date="2026-01-29",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="DEUDA",
                    amount=Decimal("80000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                # Febrero 2026: Mes con 0 ingresos y gasto operativo para probar margen 0.0% sin ZeroDivisionError
                Transaction(
                    user=self.user,
                    date="2026-02-10",
                    vertical="Consultoría",
                    transaction_type=Transaction.TransactionType.EXPENSE,
                    concept="Sueldo",
                    amount=Decimal("50000.00"),
                    currency=Transaction.Currency.ARS,
                ),
                # Transacción en USD (no debe mezclarse con el reporte ARS)
                Transaction(
                    user=self.user,
                    date="2026-01-12",
                    vertical="Consultoría",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Honorarios Internacionales",
                    amount=Decimal("3000.00"),
                    currency=Transaction.Currency.USD,
                ),
                # Transacción de otro usuario (no debe filtrarse al P&L de self.user)
                Transaction(
                    user=self.other_user,
                    date="2026-01-10",
                    vertical="Academia",
                    transaction_type=Transaction.TransactionType.INCOME,
                    concept="Cuota Alumnos",
                    amount=Decimal("9999999.00"),
                    currency=Transaction.Currency.ARS,
                ),
            ]
        )

    def test_pnl_ebitda_and_net_result_exact_decimal_calculations(self):
        self.client.force_login(self.user)
        response = self.client.get(f"{self.url}?year=2026&currency=ARS")
        self.assertEqual(response.status_code, 200)

        pnl = response.context["pnl"]
        kpis = response.context["kpis"]

        # 1. Ingresos Operativos: Enero = 1.200.000,00 | Febrero = 0,00 | Total Anual = 1.200.000,00
        self.assertEqual(pnl["total_income"]["monthly"][0], Decimal("1200000.00"))
        self.assertEqual(pnl["total_income"]["monthly"][1], Decimal("0.00"))
        self.assertEqual(pnl["total_income"]["annual_total"], Decimal("1200000.00"))
        self.assertEqual(pnl["total_income"]["vertical_pct"], Decimal("100.0"))

        # Orden de mayor a menor en Ingresos: Cuota Alumnos (1.000.000) -> Otros Ingresos (200.000)
        income_concepts = [r["concept"] for r in pnl["income_rows"]]
        self.assertEqual(income_concepts, ["Cuota Alumnos", "Otros Ingresos"])

        # 2. OPEX: Enero = 660.000,00 | Febrero = 50.000,00 | Total Anual = 710.000,00 (59.2% s/ Ingresos)
        self.assertEqual(pnl["total_opex"]["monthly"][0], Decimal("660000.00"))
        self.assertEqual(pnl["total_opex"]["monthly"][1], Decimal("50000.00"))
        self.assertEqual(pnl["total_opex"]["annual_total"], Decimal("710000.00"))
        self.assertEqual(pnl["total_opex"]["vertical_pct"], Decimal("59.2"))

        # Orden de mayor a menor en OPEX: Sueldo (450.000) -> Alquiler (200.000) -> Luz (60.000)
        opex_concepts = [r["concept"] for r in pnl["opex_rows"]]
        self.assertEqual(opex_concepts, ["Sueldo", "Alquiler", "Luz"])

        # 3. EBITDA: Enero = 1.200.000 - 660.000 = 540.000 (45.0%)
        #    Febrero = 0 - 50.000 = -50.000 (Margen 0.0% por ingresos 0)
        #    Total Anual = 1.200.000 - 710.000 = 490.000,00 (40.8%)
        self.assertEqual(pnl["ebitda"]["monthly"][0], Decimal("540000.00"))
        self.assertEqual(pnl["ebitda"]["monthly"][1], Decimal("-50000.00"))
        self.assertEqual(pnl["ebitda"]["annual_total"], Decimal("490000.00"))
        self.assertEqual(pnl["ebitda"]["vertical_pct"], Decimal("40.8"))
        self.assertEqual(pnl["ebitda_margin"]["monthly"][0], Decimal("45.0"))
        self.assertEqual(pnl["ebitda_margin"]["monthly"][1], Decimal("0.0"))
        self.assertEqual(pnl["ebitda_margin"]["annual_total"], Decimal("40.8"))

        # 4. CAPEX y Servicio de Deuda (No Operativo): Estructura (100.000) + Deuda (80.000) = 180.000,00 (15.0%)
        non_op_norms = [r["normalized_concept"] for r in pnl["non_operating_rows"]]
        self.assertEqual(non_op_norms, ["estructura", "deuda"])
        self.assertEqual(pnl["total_non_operating"]["monthly"][0], Decimal("180000.00"))
        self.assertEqual(pnl["total_non_operating"]["annual_total"], Decimal("180000.00"))
        self.assertEqual(pnl["total_non_operating"]["vertical_pct"], Decimal("15.0"))

        # 5. Resultado Neto de Caja (Flujo Libre):
        #    Enero = 540.000 - 180.000 = 360.000,00 (30.0%)
        #    Febrero = -50.000 - 0 = -50.000,00 (Margen 0.0% por ingresos 0)
        #    Total Anual = 490.000 - 180.000 = 310.000,00 (25.8%)
        self.assertEqual(pnl["net_result"]["monthly"][0], Decimal("360000.00"))
        self.assertEqual(pnl["net_result"]["monthly"][1], Decimal("-50000.00"))
        self.assertEqual(pnl["net_result"]["annual_total"], Decimal("310000.00"))
        self.assertEqual(pnl["net_result"]["vertical_pct"], Decimal("25.8"))
        self.assertEqual(pnl["net_margin"]["monthly"][0], Decimal("30.0"))
        self.assertEqual(pnl["net_margin"]["monthly"][1], Decimal("0.0"))
        self.assertEqual(pnl["net_margin"]["annual_total"], Decimal("25.8"))

        # Verificar KPIs superiores, formateo contable argentino y controles Mobile-First
        self.assertEqual(kpis["total_income"], Decimal("1200000.00"))
        self.assertEqual(kpis["total_opex"], Decimal("710000.00"))
        self.assertEqual(kpis["ebitda"], Decimal("490000.00"))
        self.assertEqual(kpis["net_result"], Decimal("310000.00"))
        self.assertContains(response, "1.200.000,00")
        self.assertContains(response, "490.000,00")
        self.assertContains(response, "310.000,00")
        self.assertContains(response, "490.000")
        self.assertContains(response, "310.000")
        self.assertContains(response, "490000.00")
        self.assertContains(response, "310000.00")
        self.assertContains(response, "0.0%")
        self.assertContains(response, 'id="btn-toggle-granularity"')
        self.assertContains(response, 'data-toggle-block="income"')
        self.assertContains(response, 'data-toggle-block="opex"')
        self.assertContains(response, 'data-toggle-block="non_operating"')
        self.assertContains(response, "pnl-table--annual-only")
        self.assertContains(response, "Vista: Consolidado Anual")
        self.assertContains(response, "Vista: Mensual (Ene-Dic)")

    def test_pnl_filters_by_vertical_and_currency(self):
        self.client.force_login(self.user)

        # Filtrar por vertical "Academia" en ARS (excluye los 50.000 de Sueldo en Consultoría de Febrero)
        res_academia = self.client.get(
            f"{self.url}?year=2026&currency=ARS&vertical=Academia"
        )
        self.assertEqual(res_academia.status_code, 200)
        pnl_acad = res_academia.context["pnl"]
        self.assertEqual(pnl_acad["total_income"]["annual_total"], Decimal("1200000.00"))
        self.assertEqual(pnl_acad["total_opex"]["annual_total"], Decimal("660000.00"))
        self.assertEqual(pnl_acad["ebitda"]["annual_total"], Decimal("540000.00"))
        self.assertEqual(pnl_acad["net_result"]["annual_total"], Decimal("360000.00"))
        self.assertEqual(pnl_acad["net_margin"]["annual_total"], Decimal("30.0"))

        # Filtrar por moneda "USD"
        res_usd = self.client.get(f"{self.url}?year=2026&currency=USD")
        self.assertEqual(res_usd.status_code, 200)
        pnl_usd = res_usd.context["pnl"]
        self.assertEqual(pnl_usd["total_income"]["annual_total"], Decimal("3000.00"))
        self.assertEqual(pnl_usd["total_opex"]["annual_total"], Decimal("0.00"))
        self.assertEqual(pnl_usd["ebitda"]["annual_total"], Decimal("3000.00"))
        self.assertEqual(pnl_usd["net_result"]["annual_total"], Decimal("3000.00"))
        self.assertEqual(pnl_usd["net_margin"]["annual_total"], Decimal("100.0"))


class VerticalsModuleAndIntegrityTests(TestCase):
    """
    11. Pruebas integrales para el módulo de Verticales de Negocio e Integridad de Datos:
        - Alta y baja lógica (is_active=False, deactivated_at) sin eliminación física.
        - Integridad referencial (on_delete=models.PROTECT) bloqueando borrados físicos.
        - Unicidad case-insensitive y sin tildes/espacios extra entre verticales activas.
        - Reactivación controlada de una vertical previamente dada de baja conservando su ID.
        - Rechazo estricto al intentar asignar una vertical inactiva por POST directo.
        - Preservación histórica al listar, exportar o editar transacciones antiguas con vertical inactiva.
        - Aislamiento estricto entre cuentas de usuario.
        - Validación de verticales activas durante la importación Excel/CSV y generación de plantilla Excel.
    """

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="director@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.other_user = CustomUser.objects.create_user(
            email="otra_cuenta@empresa.com",
            password="ContrasenaFuerte2026!",
            is_active=True,
        )
        self.verticals_url = reverse("app:verticals")
        self.tx_url = reverse("app:transactions")

    def test_create_and_logical_deactivation_of_vertical(self):
        self.client.force_login(self.user)

        # 1. Dar de alta una vertical con espacios extra
        res_create = self.client.post(
            self.verticals_url,
            {
                "action": "create",
                "title": "   Consultoría Estratégica   ",
                "description": "  Asesoramiento financiero corporativo  ",
            },
        )
        self.assertEqual(res_create.status_code, 201)
        payload = res_create.json()
        self.assertEqual(payload["status"], "ok")
        v_id = payload["vertical"]["id"]
        self.assertEqual(payload["vertical"]["title"], "Consultoría Estratégica")
        self.assertEqual(
            payload["vertical"]["description"],
            "Asesoramiento financiero corporativo",
        )
        self.assertTrue(payload["vertical"]["is_active"])

        # 2. Editar título y descripción en lote mediante "Guardar Cambios" (bulk_save)
        res_bulk_edit = self.client.post(
            self.verticals_url,
            data=json.dumps(
                {
                    "action": "bulk_save",
                    "rows": [
                        {
                            "id": v_id,
                            "title": "  Consultoría Corporativa 2026  ",
                            "description": "  Descripción modificada desde la tabla  ",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_bulk_edit.status_code, 200)
        v_db_updated = Vertical.objects.get(pk=v_id)
        self.assertEqual(v_db_updated.title, "Consultoría Corporativa 2026")
        self.assertEqual(
            v_db_updated.description, "Descripción modificada desde la tabla"
        )

        # 3. Dar de baja lógica la vertical
        res_deact = self.client.post(
            self.verticals_url,
            data=json.dumps({"action": "deactivate", "id": v_id}),
            content_type="application/json",
        )
        self.assertEqual(res_deact.status_code, 200)
        data_deact = res_deact.json()
        self.assertEqual(data_deact["status"], "ok")
        self.assertEqual(data_deact["deactivated_id"], v_id)
        self.assertEqual(len(data_deact["verticals"]), 0)

        # Verificar que sigue existiendo físicamente en la base de datos con is_active=False
        v_db = Vertical.objects.get(pk=v_id)
        self.assertFalse(v_db.is_active)
        self.assertIsNotNone(v_db.deactivated_at)

        # La interfaz GET de Verticales solo lista verticales activas
        res_get = self.client.get(self.verticals_url)
        self.assertEqual(res_get.status_code, 200)
        self.assertNotContains(res_get, "Consultoría Corporativa 2026")

    def test_case_insensitive_and_accent_insensitive_uniqueness_and_controlled_reactivation(
        self,
    ):
        self.client.force_login(self.user)
        v_orig = Vertical.objects.create(
            user=self.user,
            title="Consultoría",
            description="Descripción inicial",
            is_active=True,
        )

        # 1. Intentar crear duplicado activo con distintas mayúsculas, espacios o sin tilde
        for duplicate_title in ("CONSULTORÍA", "  consultoría  ", " consultoria "):
            res_dup = self.client.post(
                self.verticals_url,
                {
                    "action": "create",
                    "title": duplicate_title,
                    "description": "Duplicada",
                },
            )
            self.assertEqual(res_dup.status_code, 400)
            self.assertIn(
                "Ya existe una vertical activa con este título",
                res_dup.json()["message"],
            )

        self.assertEqual(Vertical.objects.filter(user=self.user).count(), 1)

        # 2. Dar de baja lógica la vertical y volver a darla de alta -> Reactivación controlada conservando ID
        v_orig.deactivate()
        self.assertFalse(v_orig.is_active)

        res_reactivate = self.client.post(
            self.verticals_url,
            {
                "action": "create",
                "title": "  CONSULTORÍA ",
                "description": "Descripción actualizada al reactivar",
            },
        )
        self.assertEqual(res_reactivate.status_code, 200)
        react_data = res_reactivate.json()
        self.assertTrue(react_data["reactivated"])
        self.assertEqual(react_data["vertical"]["id"], v_orig.id)

        v_orig.refresh_from_db()
        self.assertTrue(v_orig.is_active)
        self.assertIsNone(v_orig.deactivated_at)
        self.assertEqual(
            v_orig.description, "Descripción actualizada al reactivar"
        )
        self.assertEqual(Vertical.objects.filter(user=self.user).count(), 1)

    def test_on_delete_protect_prevents_physical_deletion_of_vertical_with_transactions(
        self,
    ):
        v = Vertical.objects.create(
            user=self.user, title="Academia", is_active=True
        )
        Transaction.objects.create(
            user=self.user,
            date="2026-11-10",
            vertical=v,
            transaction_type=Transaction.TransactionType.INCOME,
            concept="Cuota Mensual",
            amount=Decimal("50000.00"),
            currency=Transaction.Currency.ARS,
        )

        # Intento de borrado físico directo desde ORM/Admin debe lanzar ProtectedError
        with self.assertRaises(ProtectedError):
            v.delete()

        self.assertTrue(Vertical.objects.filter(pk=v.pk).exists())

    def test_cannot_assign_inactive_vertical_via_direct_post_to_new_or_other_transaction(
        self,
    ):
        self.client.force_login(self.user)
        v_active = Vertical.objects.create(
            user=self.user, title="Activa", is_active=True
        )
        v_inactive = Vertical.objects.create(
            user=self.user, title="Dada de Baja", is_active=False
        )

        # 1. Intentar crear una nueva transacción asignando el ID o título de una vertical inactiva
        res_new_by_id = self.client.post(
            self.tx_url,
            data=json.dumps(
                {
                    "action": "create",
                    "date": "2026-11-15",
                    "vertical": v_inactive.id,
                    "transaction_type": "INGRESO",
                    "concept": "Venta",
                    "amount": "1000.00",
                    "currency": "ARS",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_new_by_id.status_code, 400)
        self.assertIn("inactiva", res_new_by_id.json()["message"].lower())
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        res_new_by_title = self.client.post(
            self.tx_url,
            data=json.dumps(
                {
                    "action": "create",
                    "date": "2026-11-15",
                    "vertical": "Dada de Baja",
                    "transaction_type": "INGRESO",
                    "concept": "Venta",
                    "amount": "1000.00",
                    "currency": "ARS",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_new_by_title.status_code, 400)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        # 2. Crear transacción con vertical activa y luego intentar cambiarla a una vertical inactiva
        tx = Transaction.objects.create(
            user=self.user,
            date="2026-11-15",
            vertical=v_active,
            transaction_type=Transaction.TransactionType.INCOME,
            concept="Venta Válida",
            amount=Decimal("2500.00"),
            currency=Transaction.Currency.ARS,
        )
        res_change_to_inactive = self.client.post(
            self.tx_url,
            data=json.dumps(
                {
                    "action": "update",
                    "id": tx.id,
                    "date": "2026-11-15",
                    "vertical": v_inactive.id,
                    "transaction_type": "INGRESO",
                    "concept": "Venta Válida",
                    "amount": "2500.00",
                    "currency": "ARS",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_change_to_inactive.status_code, 400)
        tx.refresh_from_db()
        self.assertEqual(tx.vertical_id, v_active.id)

    def test_historical_transaction_preserves_inactive_vertical_on_edit_list_and_export(
        self,
    ):
        self.client.force_login(self.user)
        v_hist = Vertical.objects.create(
            user=self.user, title="Línea Legacy 2025", is_active=True
        )
        v_current = Vertical.objects.create(
            user=self.user, title="Línea Actual 2026", is_active=True
        )

        # Crear transacción cuando la vertical estaba activa
        tx = Transaction.objects.create(
            user=self.user,
            date="2025-06-10",
            vertical=v_hist,
            transaction_type=Transaction.TransactionType.INCOME,
            concept="Cobro Histórico",
            detail="Detalle original",
            amount=Decimal("85000.00"),
            currency=Transaction.Currency.ARS,
        )

        # Dar de baja lógica la vertical histórica
        v_hist.deactivate()

        # 1. Al renderizar la vista de Transacciones, el selector de esa fila incluye la vertical marcada como (Inactiva)
        res_list = self.client.get(self.tx_url)
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Línea Legacy 2025 (Inactiva)")
        self.assertContains(res_list, "Línea Actual 2026")

        # 2. Al editar otros campos de la transacción histórica (ej. monto o detalle) manteniendo su vertical inactiva, se guarda sin perderla
        res_edit = self.client.post(
            self.tx_url,
            data=json.dumps(
                {
                    "action": "bulk_save",
                    "rows": [
                        {
                            "id": tx.id,
                            "date": "2025-06-10",
                            "vertical": v_hist.id,
                            "transaction_type": "INGRESO",
                            "concept": "Cobro Histórico Ajustado",
                            "client": "",
                            "detail": "Detalle editado sin perder vertical inactiva",
                            "amount": "90000.00",
                            "currency": "ARS",
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_edit.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.vertical_id, v_hist.id)
        self.assertEqual(tx.concept, "Cobro Histórico Ajustado")
        self.assertEqual(tx.amount, Decimal("90000.00"))

        # 3. Al exportar transacciones a Excel, se preserva el nombre de la vertical histórica
        res_export = self.client.get(reverse("app:transactions_export"))
        self.assertEqual(res_export.status_code, 200)
        df_export = pd.read_excel(
            io.BytesIO(res_export.content),
            sheet_name="Transacciones",
            engine="openpyxl",
        )
        self.assertEqual(len(df_export), 1)
        self.assertEqual(df_export.iloc[0]["Vertical"], "Línea Legacy 2025")
        self.assertEqual(df_export.iloc[0]["Estado_Vertical"], "Inactiva")

    def test_strict_user_isolation_for_verticals_and_transactions(self):
        v_other = Vertical.objects.create(
            user=self.other_user, title="Vertical Ajena", is_active=True
        )
        self.client.force_login(self.user)

        # 1. No puede ver ni dar de baja la vertical de otro usuario
        res_get = self.client.get(self.verticals_url)
        self.assertNotContains(res_get, "Vertical Ajena")

        res_deact = self.client.post(
            self.verticals_url,
            data=json.dumps({"action": "deactivate", "id": v_other.id}),
            content_type="application/json",
        )
        self.assertEqual(res_deact.status_code, 404)
        v_other.refresh_from_db()
        self.assertTrue(v_other.is_active)

        # 2. No puede asignar el ID de la vertical de otro usuario a una transacción propia
        res_tx = self.client.post(
            self.tx_url,
            data=json.dumps(
                {
                    "action": "create",
                    "date": "2026-11-20",
                    "vertical": v_other.id,
                    "transaction_type": "INGRESO",
                    "concept": "Intento Cruzado",
                    "amount": "500.00",
                    "currency": "ARS",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res_tx.status_code, 400)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_excel_and_csv_import_validates_active_verticals_and_template_reflects_active_verticals(
        self,
    ):
        self.client.force_login(self.user)
        v_active = Vertical.objects.create(
            user=self.user,
            title="Consultoría",
            description="Unidad activa",
            is_active=True,
        )
        v_inactive = Vertical.objects.create(
            user=self.user,
            title="Unidad Cerrada",
            description="Dada de baja",
            is_active=False,
        )
        Vertical.objects.create(
            user=self.other_user,
            title="Vertical Otro Usuario",
            is_active=True,
        )

        # 1. Verificar que la plantilla Excel incluye únicamente las verticales activas del usuario
        res_tpl = self.client.get(reverse("app:transactions_template"))
        self.assertEqual(res_tpl.status_code, 200)
        df_vert_sheet = pd.read_excel(
            io.BytesIO(res_tpl.content),
            sheet_name="Verticales_Activas",
            engine="openpyxl",
        )
        active_titles = list(df_vert_sheet["Vertical"])
        self.assertEqual(active_titles, ["Consultoría"])
        self.assertNotIn("Unidad Cerrada", active_titles)
        self.assertNotIn("Vertical Otro Usuario", active_titles)

        # 2. Importar fila con vertical inexistente debe fallar indicando fila y motivo, sin crear verticales fantasma
        csv_missing_vert = (
            "Fecha,Vertical,Tipo,Concepto,Cliente,Detalle,Monto,Moneda\n"
            "2026-11-01,Vertical Fantasma,Ingreso,Abono,Cliente A,Detalle,1000.00,ARS\n"
        ).encode("utf-8")
        res_missing = self.client.post(
            self.tx_url,
            {
                "action": "bulk_upload",
                "file": SimpleUploadedFile(
                    "fantasma.csv", csv_missing_vert, content_type="text/csv"
                ),
            },
        )
        self.assertEqual(res_missing.status_code, 400)
        msg_missing = res_missing.json()["message"]
        self.assertIn("Fila 2", msg_missing)
        self.assertIn("Vertical Fantasma", msg_missing)
        self.assertFalse(
            Vertical.objects.filter(title__iexact="Vertical Fantasma").exists()
        )
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        # 3. Importar fila con vertical dada de baja (is_active=False) debe ser rechazado con error descriptivo
        csv_inactive_vert = (
            "Fecha,Vertical,Tipo,Concepto,Cliente,Detalle,Monto,Moneda\n"
            "2026-11-01,  UNIDAD CERRADA ,Ingreso,Abono,Cliente A,Detalle,1000.00,ARS\n"
        ).encode("utf-8")
        res_inact = self.client.post(
            self.tx_url,
            {
                "action": "bulk_upload",
                "file": SimpleUploadedFile(
                    "inactiva.csv", csv_inactive_vert, content_type="text/csv"
                ),
            },
        )
        self.assertEqual(res_inact.status_code, 400)
        msg_inact = res_inact.json()["message"]
        self.assertIn("Fila 2", msg_inact)
        self.assertIn("dada de baja", msg_inact.lower())
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        # 4. Importar fila con vertical activa (comparación case-insensitive y sin espacios sobrantes) tiene éxito
        csv_valid_vert = (
            "Fecha,Vertical,Tipo,Concepto,Cliente,Detalle,Monto,Moneda\n"
            "2026-11-01,  consultoria  ,Ingreso,Abono,Cliente A,Detalle,1000.00,ARS\n"
        ).encode("utf-8")
        res_valid = self.client.post(
            self.tx_url,
            {
                "action": "bulk_upload",
                "file": SimpleUploadedFile(
                    "valida.csv", csv_valid_vert, content_type="text/csv"
                ),
            },
        )
        self.assertEqual(res_valid.status_code, 200)
        tx_created = Transaction.objects.get(user=self.user)
        self.assertEqual(tx_created.vertical_id, v_active.id)

