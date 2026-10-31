from django.test import SimpleTestCase
from django.urls import reverse


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

        # Header
        self.assertContains(response, "Tomas Cueva")
        self.assertContains(response, "Iniciar sesión")

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
