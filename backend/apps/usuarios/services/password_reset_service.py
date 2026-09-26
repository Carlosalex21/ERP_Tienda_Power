"""
Recuperación de contraseña para los usuarios de un tenant (empleados,
administrador del negocio). Antes no existía ninguna forma de recuperar el
acceso si alguien olvidaba su contraseña -- quedaba fuera del sistema sin
remedio salvo pedirle a otro admin que se la cambiara a mano.

Usa el `PasswordResetTokenGenerator` estándar de Django (el mismo mecanismo
que `django.contrib.auth`): el token es válido una sola vez y expira solo
(por defecto según `PASSWORD_RESET_TIMEOUT`, 3 días) o en cuanto la
contraseña cambia.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from .sesiones_service import revocar_sesiones

token_generator = PasswordResetTokenGenerator()


def solicitar_reset(email: str, tenant_frontend_url: str) -> None:
    """
    Envía el correo de recuperación si el email pertenece a un usuario de
    este tenant. Nunca revela si el email existe o no (evita enumeración).
    """
    User = get_user_model()
    try:
        user = User.objects.get(email__iexact=email.strip())
    except User.DoesNotExist:
        return

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)
    link = f"{tenant_frontend_url}/reset-password?uid={uid}&token={token}"

    send_mail(
        subject="Recupera tu contraseña",
        message=(
            f"Hola {user.first_name or user.username},\n\n"
            f"Usa este enlace para elegir una nueva contraseña:\n{link}\n\n"
            "Si tú no solicitaste esto, puedes ignorar este correo."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@erpsystem.local"),
        recipient_list=[user.email],
        fail_silently=True,
    )


class ResetTokenInvalidoError(Exception):
    """El enlace de recuperación es inválido, ya se usó, o expiró."""


def confirmar_reset(uid: str, token: str, nueva_password: str):
    """Valida el token y cambia la contraseña del usuario. Devuelve el `User`."""
    User = get_user_model()
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        raise ResetTokenInvalidoError("El enlace de recuperación no es válido.")

    if not token_generator.check_token(user, token):
        raise ResetTokenInvalidoError("El enlace expiró o ya fue utilizado. Solicita uno nuevo.")

    user.set_password(nueva_password)
    user.save(update_fields=["password"])
    # Quien recupera su cuenta por correo probablemente perdió el control de
    # ella: se cierran todas las sesiones abiertas con la contraseña vieja.
    revocar_sesiones(user)
    return user
