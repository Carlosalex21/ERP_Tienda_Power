"""
Lógica para registrar y comparar el estado de un objeto auditado.

`_snapshot`/`_valor_serializable` existen porque `model_to_dict` deja campos
no serializables tal cual (Decimal, datetime, archivos) -- un `JSONField` no
los puede guardar directo.
"""
from __future__ import annotations

import datetime
import decimal
from typing import Any

from django.db.models import Model
from django.db.models.fields.files import FieldFile
from django.forms.models import model_to_dict

from .middleware import get_current_ip, get_current_user
from .models import RegistroAuditoria


def _valor_serializable(valor: Any) -> Any:
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return valor.isoformat()
    if isinstance(valor, FieldFile):
        # FieldFile (ImageField/FileField): no serializa a JSON tal cual, y
        # acceder a `.url` sin archivo asociado lanza ValueError (no
        # AttributeError) -- por eso se chequea el tipo, no con hasattr().
        return valor.name or None
    if isinstance(valor, Model):
        return valor.pk
    if isinstance(valor, (list, tuple)):
        return [_valor_serializable(v) for v in valor]
    return valor


def snapshot(instancia: Model) -> dict:
    """Foto plana de los campos del modelo (FK -> pk, M2M -> lista de pks)."""
    try:
        datos = model_to_dict(instancia)
    except Exception:
        return {}
    return {campo: _valor_serializable(valor) for campo, valor in datos.items()}


def diferencias(antes: dict, despues: dict) -> dict:
    cambios = {}
    for campo, valor_nuevo in despues.items():
        valor_anterior = antes.get(campo)
        if valor_anterior != valor_nuevo:
            cambios[campo] = {'antes': valor_anterior, 'despues': valor_nuevo}
    return cambios


def registrar(accion: str, instancia: Model, cambios: dict | None = None, usuario=None) -> RegistroAuditoria:
    """Crea un registro de auditoría para `instancia`. `usuario=None` toma el usuario de la petición en curso."""
    user = usuario if usuario is not None else get_current_user()
    user_obj = user if user is not None and getattr(user, 'is_authenticated', False) else None
    if user_obj is not None:
        nombre = user_obj.get_full_name() or user_obj.get_username()
    else:
        nombre = 'Sistema'

    return RegistroAuditoria.objects.create(
        usuario=user_obj,
        usuario_nombre=nombre,
        accion=accion,
        modelo=instancia.__class__.__name__,
        objeto_id=str(instancia.pk),
        objeto_repr=str(instancia)[:255],
        cambios=cambios,
        ip_address=get_current_ip(),
    )
