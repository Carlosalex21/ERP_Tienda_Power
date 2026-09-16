"""
Conecta `pre_save`/`post_save`/`post_delete` para el conjunto de modelos
"auditables" -- deliberadamente NO es automático para todo el ORM: modelos
de alto volumen y bajo valor de auditoría (ej. `TasaCambio`, que se
actualiza sola a diario desde el BCV) quedan fuera a propósito para no
inundar la auditoría con ruido y enterrar lo que sí importa.

Por qué señales y no llamadas explícitas en cada vista/servicio: así la
auditoría queda desacoplada de la lógica de negocio -- anular una factura,
cambiar el correlativo, editar un producto, todo se captura solo, sin tener
que acordarse de instrumentar cada punto de guardado uno por uno (y sin
arriesgarse a que alguien olvide hacerlo en un service nuevo).
"""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.clientes.models import Cliente
from apps.configuracion.models import ConfiguracionCorrelativo, ConfiguracionEmpresa
from apps.facturacion.models import (
    Detallefactura,
    Factura,
    MetodoPago,
    NotaCredito,
    NotaDebito,
    Retencion,
    Transaccionpago,
)
from apps.inventario.models import Producto, Variacionproducto
from apps.pagos.models import TransaccionPasarela
from apps.proveedores.models import Proveedor

from .models import RegistroAuditoria
from .services import diferencias, registrar, snapshot

AUDITED_MODELS = (
    Factura,
    Detallefactura,
    NotaCredito,
    NotaDebito,
    Retencion,
    Transaccionpago,
    MetodoPago,
    Producto,
    Variacionproducto,
    Cliente,
    Proveedor,
    ConfiguracionEmpresa,
    ConfiguracionCorrelativo,
    TransaccionPasarela,
)

_ANTERIOR_ATTR = '_auditoria_snapshot_anterior'


@receiver(pre_save)
def _capturar_estado_anterior(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    if not instance.pk:
        setattr(instance, _ANTERIOR_ATTR, None)
        return
    try:
        anterior = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        setattr(instance, _ANTERIOR_ATTR, None)
    else:
        setattr(instance, _ANTERIOR_ATTR, snapshot(anterior))


@receiver(post_save)
def _registrar_guardado(sender, instance, created, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    if isinstance(instance, RegistroAuditoria):
        return  # evita recursión: crear un registro de auditoría no genera otro.

    if created:
        registrar(RegistroAuditoria.ACCION_CREAR, instance)
        return

    anterior = getattr(instance, _ANTERIOR_ATTR, None)
    if anterior is None:
        return  # no había estado previo capturado (raro, pero no hay con qué comparar).

    cambios = diferencias(anterior, snapshot(instance))
    if not cambios:
        return

    # Baja/reactivación lógica (`activo`) es semánticamente distinta de una
    # edición cualquiera -- se etiqueta aparte para que sea fácil de
    # encontrar en la auditoría ("¿quién desactivó este producto?").
    if set(cambios.keys()) == {'activo'}:
        paso_a_false = cambios['activo']['despues'] is False
        accion = RegistroAuditoria.ACCION_ELIMINAR if paso_a_false else RegistroAuditoria.ACCION_REACTIVAR
    else:
        accion = RegistroAuditoria.ACCION_ACTUALIZAR

    registrar(accion, instance, cambios=cambios)


@receiver(post_delete)
def _registrar_borrado_fisico(sender, instance, **kwargs):
    # Con las bajas convertidas a lógicas (`activo=False`) para los modelos
    # fiscales/de inventario (ver `perform_destroy` en cada ViewSet), esto
    # solo debería dispararse para modelos que todavía permiten borrado
    # físico real -- se deja como red de seguridad para que, si alguno
    # llega a borrarse de verdad (shell, migración, etc.), quede igual
    # trazado en vez de desaparecer sin dejar rastro.
    if sender not in AUDITED_MODELS:
        return
    registrar(RegistroAuditoria.ACCION_ELIMINAR, instance)
