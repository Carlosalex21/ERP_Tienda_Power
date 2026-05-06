# apps/inventario/api/views_operaciones.py
from rest_framework import viewsets, permissions
from erp.models import MovimientoInventario, Reservastock, Lecturacodigobarras
from apps.inventario.api.serializers import MovimientoInventarioSerializer, ReservastockSerializer, LecturacodigobarrasSerializer

class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    queryset = MovimientoInventario.objects.all().order_by("-fecha_movimiento")
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [permissions.IsAuthenticated]

class ReservastockViewSet(viewsets.ModelViewSet):
    queryset = Reservastock.objects.all().order_by("-fecha_creacion")
    serializer_class = ReservastockSerializer
    permission_classes = [permissions.IsAuthenticated]

class LecturacodigobarrasViewSet(viewsets.ModelViewSet):
    queryset = Lecturacodigobarras.objects.all().order_by("-fecha_lectura")
    serializer_class = LecturacodigobarrasSerializer
    permission_classes = [permissions.IsAuthenticated]