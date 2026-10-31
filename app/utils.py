"""
Utilidades de la aplicación app.
Implementa el envío de correos electrónicos no bloqueante mediante threading estándar
sin sobrecargar la memoria RAM con colas pesadas (Celery/Redis).
"""

import logging
import threading
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


class AsyncEmailSender(threading.Thread):
    """
    Hilo en segundo plano para despachar correos electrónicos sin bloquear
    los workers de Gunicorn durante el ciclo de petición HTTP.
    """

    def __init__(
        self,
        subject,
        body,
        from_email,
        recipient_list,
        fail_silently=False,
        html_message=None,
    ):
        super().__init__(daemon=True)
        self.subject = subject
        self.body = body
        self.from_email = from_email
        self.recipient_list = recipient_list
        self.fail_silently = fail_silently
        self.html_message = html_message

    def run(self):
        try:
            send_mail(
                subject=self.subject,
                message=self.body,
                from_email=self.from_email,
                recipient_list=self.recipient_list,
                fail_silently=self.fail_silently,
                html_message=self.html_message,
            )
        except Exception:
            logger.exception(
                "Error al enviar correo electrónico asíncrono a %s",
                self.recipient_list,
            )


def send_async_email(subject, body, to_email, html_message=None):
    """
    Envía un correo electrónico utilizando AsyncEmailSender en producción.
    Durante la ejecución de pruebas (TESTING=True o mail.outbox activo),
    ejecuta send_mail de forma síncrona para garantizar determinismo.
    """
    recipient_list = [to_email] if isinstance(to_email, str) else list(to_email)
    from_email = getattr(
        settings, "DEFAULT_FROM_EMAIL", "sistema@accountingdata.local"
    )

    if getattr(settings, "TESTING", False) or hasattr(mail, "outbox"):
        return send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
            html_message=html_message,
        )

    sender = AsyncEmailSender(
        subject=subject,
        body=body,
        from_email=from_email,
        recipient_list=recipient_list,
        fail_silently=False,
        html_message=html_message,
    )
    sender.start()
    return sender


def send_activation_email(request, user):
    """
    Construye el enlace absoluto de activación con UID en base64 y token seguro,
    renderiza la plantilla de correo y despacha el mensaje.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_path = reverse(
        "app:activate_account", kwargs={"uidb64": uid, "token": token}
    )
    activation_url = request.build_absolute_uri(activation_path)

    subject = "Confirmación de cuenta — Sistema Financiero"
    body = render_to_string(
        "app/auth/emails/activate_account_email.txt",
        {
            "user": user,
            "activation_url": activation_url,
            "uid": uid,
            "token": token,
        },
    )
    return send_async_email(subject=subject, body=body, to_email=user.email)
