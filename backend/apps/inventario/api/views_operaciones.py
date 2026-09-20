# apps/inventario/api/views_operaciones.py
from rest_framework import viewsets, permissions
from apps.inventario.models import MovimientoInventario, Reservastock, Lecturacodigobarras
from apps.inventario.api.serializers import MovimientoInventarioSerializer, ReservastockSerializer, LecturacodigobarrasSerializer

# Los tres modelos de este archivo son registros operativos/de auditoría
# (movimientos de stock, reservas, lecturas de código de barras) que el
# sistema genera SOLO desde services internos (ventas, ajustes, reducción
# de stock) -- ningún flujo del frontend los crea/edita/borra directo por
# la API (nada en `ERP_System_Persona/src` llama a estos endpoints). Antes
# eran `ModelViewSet` completos con solo `IsAuthenticated`: cualquier
# empleado logueado podía escribir/editar/BORRAR el historial de
# movimientos de inventario a mano, sin pasar por el flujo auditado de
# `AjusteInventarioViewSet` (ver `views_ajustes.py`). Se dejan de solo
# lectura, igual que ya se hace ahí para los ajustes ya aplicados.
class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = MovimientoInventario.objects.all().order_by("-fecha_movimiento")
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [permissions.IsAuthenticated]

class ReservastockViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = Reservastock.objects.all().order_by("-fecha_creacion")
    serializer_class = ReservastockSerializer
    permission_classes = [permissions.IsAuthenticated]

class LecturacodigobarrasViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = Lecturacodigobarras.objects.all().order_by("-fecha_lectura")
    serializer_class = LecturacodigobarrasSerializer
    permission_classes = [permissions.IsAuthenticated]