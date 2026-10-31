"""
Suite de pruebas unitarias y de integración para la aplicación app.
Cubre la Landing Page, el modelo CustomUser y los flujos completos de autenticación.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

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
        self.assertRedirects(response, reverse("app:home"))
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
