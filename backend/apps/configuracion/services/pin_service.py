"""
PIN de autorización para eliminar renglones (ej. un cajero quitando un
producto ya agregado al POS, o un mesero quitando un ítem de una mesa) --
un control opcional que el admin activa si su negocio lo necesita.

Se guarda hasheado (igual que una contraseña, vía
`django.contrib.auth.hashers`) para no dejarlo en texto plano en la base de
datos; nunca se expone el hash ni el PIN en ninguna respuesta de la API, solo
el resultado booleano de verificarlo.
"""
from django.contrib.auth.hashers import check_password, make_password

from ..models import ConfiguracionEmpresa


def establecer_pin(pin: str) -> None:
    config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
    config.pin_autorizacion_hash = make_password(pin)
    config.save(update_fields=['pin_autorizacion_hash'])


def verificar_pin(pin: str) -> bool:
    config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
    if not config.pin_autorizacion_hash or not pin:
        return False
    return check_password(pin, config.pin_autorizacion_hash)
