"""
Integración con DolarAPI (https://dolarapi.com) para traer automáticamente
la tasa oficial del BCV (Banco Central de Venezuela) y evitar que el
usuario tenga que cargar la tasa manualmente todos los días.

Solo aplica a tenants configurados como Venezuela (``pais_codigo == 'VE'``,
ver ``config_service.obtener_pais_tenant``): para el resto de países esta
fuente no tiene sentido.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

import requests

from ..core.config_service import obtener_pais_tenant
from ..models import Moneda, TasaCambio

logger = logging.getLogger(__name__)

DOLARAPI_URL = "https://ve.dolarapi.com/v1/dolares/oficial"
FUENTE_BCV = "BCV (dolarapi.com)"


class BcvApiError(Exception):
    """La consulta a DolarAPI falló o devolvió un dato inutilizable."""


def obtener_tasa_bcv_oficial() -> Decimal:
    """Consulta la tasa oficial (BCV) vigente en DolarAPI."""
    try:
        respuesta = requests.get(DOLARAPI_URL, timeout=6)
        respuesta.raise_for_status()
        data = respuesta.json()
        promedio = data.get("promedio")
        if promedio is None:
            raise BcvApiError("DolarAPI no devolvió el campo 'promedio'.")
        return Decimal(str(promedio))
    except (requests.RequestException, ValueError, InvalidOperation, TypeError) as exc:
        raise BcvApiError(f"No se pudo consultar la tasa oficial del BCV: {exc}") from exc


# Recuerda, por moneda, el último día en que YA se verificó si hacía falta
# actualizar. Vive en memoria del proceso (no en Redis): si Redis está caído,
# `cache_utils` degrada a "sin caché" y esta función se ejecutaría en cada
# request sin este freno -- terminaría golpeando la API externa todo el
# tiempo. Con este diccionario en memoria, el peor caso es una verificación
# de más por proceso/worker al día, intrascendente para una API pública.
_ultima_verificacion: dict[str, date] = {}


def asegurar_tasa_bcv_del_dia(*, forzar: bool = False) -> TasaCambio | None:
    """
    Si el tenant es venezolano y tiene USD configurado como moneda no-base,
    garantiza que exista una tasa de HOY tomada del BCV.

    Se llama como efecto colateral de ``conversion_service.get_tasa_vigente
    ('USD')``, así que corre sola con el tráfico normal del día (POS,
    facturación, etc.) -- sin tareas periódicas ni infraestructura adicional
    (Celery Beat). No pisa una tasa manual que el usuario ya haya cargado
    hoy, salvo que se pase ``forzar=True`` (botón "Actualizar desde BCV").

    Args:
        forzar: Si es True, ignora el freno de "una vez al día" y la
            existencia de una tasa de hoy, y deja propagar ``BcvApiError``
            en vez de tragárselo -- pensado para una acción explícita del
            usuario, que sí necesita saber si algo salió mal.

    Returns:
        La ``TasaCambio`` recién creada, o ``None`` si no aplicaba o ya
        existía una tasa de hoy (y no se forzó).
    """
    if obtener_pais_tenant() != "VE":
        if forzar:
            raise BcvApiError("Esta función solo aplica a tenants configurados como Venezuela.")
        return None

    # OJO: `date.today()` (no `timezone.now().date()`) a propósito -- es
    # justo lo que usa `DateField(auto_now_add=True)` internamente
    # (`django.db.models.fields.DateField.pre_save`, que llama a
    # `datetime.date.today()` sin pasar por `TIME_ZONE`/`USE_TZ`). Con
    # `TIME_ZONE="UTC"` y el sistema operativo en otra zona horaria,
    # `timezone.now().date()` puede adelantarse un día respecto al `fecha`
    # que en verdad quedó grabado en `TasaCambio` -- eso hacía que "ya existe
    # una tasa de hoy" nunca calzara y se repitiera la consulta a la API.
    hoy = date.today()
    if not forzar:
        if _ultima_verificacion.get("USD") == hoy:
            return None
        _ultima_verificacion["USD"] = hoy

    moneda = Moneda.objects.filter(codigo="USD", activa=True, es_predeterminada=False).first()
    if moneda is None:
        if forzar:
            raise BcvApiError("Configura primero USD como moneda del tenant (Configuración > Monedas).")
        return None

    if not forzar and TasaCambio.objects.filter(moneda=moneda, fecha=hoy).exists():
        return None

    if forzar:
        tasa_valor = obtener_tasa_bcv_oficial()
    else:
        try:
            tasa_valor = obtener_tasa_bcv_oficial()
        except BcvApiError as exc:
            logger.warning("No se pudo actualizar la tasa BCV automáticamente: %s", exc)
            return None

    tasa = TasaCambio.objects.create(moneda=moneda, tasa=tasa_valor, fuente=FUENTE_BCV, activa=True)

    from .conversion_service import invalidar_tasas_cambio
    invalidar_tasas_cambio()

    return tasa
