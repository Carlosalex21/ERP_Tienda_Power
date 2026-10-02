"""
En qué almacén entra o sale la mercancía de un movimiento cargado por un
usuario (ajustes de inventario, facturas de compra):

- Un administrador elige cualquiera.
- Cualquier otro rol (almacenista) queda atado a su almacén operativo
  (`UserMetadata.almacen_asignado`) -- no puede cargarle stock a otra
  sucursal, aunque mande otro id.
- Sin almacén indicado se asume el del empleado; si el tenant tiene uno
  solo, ese. Con varios y sin forma de saberlo, se pide explícitamente en
  vez de dejar el movimiento "sin sucursal".
"""
from rest_framework import serializers

from apps.core.permissions import ROL_ADMIN, codigo_rol
from apps.inventario.models import Almacen


def resolver_almacen_operativo(user, almacen):
    metadata = getattr(user, 'metadata', None)
    es_admin = bool(metadata) and codigo_rol(metadata.rol) == ROL_ADMIN
    almacen_propio = getattr(metadata, 'almacen_asignado', None)

    if not es_admin and almacen_propio is not None:
        if almacen is not None and almacen.pk != almacen_propio.pk:
            raise serializers.ValidationError({
                'almacen': f'Solo puedes registrar movimientos en tu almacén asignado ({almacen_propio.nombre}).',
            })
        return almacen_propio

    if almacen is None:
        almacen = almacen_propio
    if almacen is None:
        activos = list(Almacen.objects.filter(activo=True)[:2])
        if len(activos) == 1:
            almacen = activos[0]
        elif len(activos) > 1:
            raise serializers.ValidationError({'almacen': 'Indica en qué almacén entra o sale esta mercancía.'})
    return almacen
