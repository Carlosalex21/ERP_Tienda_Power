# apps/proveedores/core/proveedores_service.py
from django.db import transaction
from apps.proveedores.models import Proveedor
# from apps.proveedores.models import Pedidoproveedor (Ejemplo)

def desactivar_proveedor_service(proveedor_id):
    """
    Lógica de negocio para "eliminar" (desactivar) un proveedor.
    """
    try:
        proveedor = Proveedor.objects.get(id=proveedor_id, activo=True)
        
        # --- LÓGICA DE NEGOCIO FUTURA AQUÍ ---
        # Ejemplo: Verificar si hay pedidos pendientes antes de desactivar
        # pedidos_pendientes = Pedidoproveedor.objects.filter(proveedor=proveedor, estado='pendiente').exists()
        # if pedidos_pendientes:
        #     raise ValueError("No se puede desactivar un proveedor con pedidos pendientes.")
        
        proveedor.activo = False
        proveedor.save(update_fields=['activo'])
        return proveedor
        
    except Proveedor.DoesNotExist:
        raise ValueError("El proveedor no existe o ya está inactivo.")

def verificar_limite_credito(proveedor_id, monto_nuevo_pedido):
    """
    Ejemplo de un servicio adicional útil para el futuro.
    """
    pass