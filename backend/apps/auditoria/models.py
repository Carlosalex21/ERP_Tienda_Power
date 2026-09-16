"""
Registro de auditoría del tenant.

Pensado para poder responder a una fiscalización (SENIAT en Venezuela, DIAN
en Colombia, SUNAT en Perú, etc.): quién hizo qué, cuándo, y qué valores
tenía el registro antes/después. El principio -- "todo cambio a un
documento o dato fiscal debe quedar trazado y ser irreversible" -- es el
mismo en los tres países, aunque el detalle de cada régimen fiscal difiera
(por eso este modelo no tiene nada específico de un país: es la base común
que cualquier auditoría, en cualquiera de los tres, necesita poder mostrar).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    ACCION_CREAR = 'crear'
    ACCION_ACTUALIZAR = 'actualizar'
    ACCION_ELIMINAR = 'eliminar'
    ACCION_REACTIVAR = 'reactivar'
    ACCION_CHOICES = (
        (ACCION_CREAR, 'Creación'),
        (ACCION_ACTUALIZAR, 'Actualización'),
        (ACCION_ELIMINAR, 'Baja / eliminación'),
        (ACCION_REACTIVAR, 'Reactivación'),
    )

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    # SET_NULL (no CASCADE): si el usuario se elimina algún día, sus
    # registros de auditoría deben sobrevivir -- por eso además se guarda
    # `usuario_nombre` como una foto fija del nombre en el momento del hecho.
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    usuario_nombre = models.CharField(max_length=150, blank=True, default='')
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES, db_index=True)
    modelo = models.CharField(max_length=100, db_index=True, help_text="Nombre del modelo afectado, ej. 'Factura'.")
    objeto_id = models.CharField(max_length=50, blank=True, default='')
    objeto_repr = models.CharField(max_length=255, blank=True, default='', help_text="Representación legible, ej. 'Factura F-011'.")
    # {"campo": {"antes": ..., "despues": ...}, ...} -- null en altas (no
    # tiene sentido un "antes" cuando el registro nace).
    cambios = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'RegistroAuditoria'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['modelo', 'objeto_id']),
        ]
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'

    def __str__(self) -> str:
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {self.usuario_nombre or 'Sistema'} · {self.accion} · {self.objeto_repr or self.modelo}"

    def delete(self, *args, **kwargs):
        # Un registro de auditoría que se puede borrar no sirve para auditar
        # nada -- se bloquea a nivel de modelo (además de no exponer delete
        # en el ViewSet/Admin) para que ni siquiera un script interno pueda
        # hacerlo por accidente vía `instance.delete()`.
        raise PermissionError("Los registros de auditoría son inmutables: no se pueden eliminar.")
