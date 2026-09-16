from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from ..models import Banco, MetodoPagoConfig, PagoMovilConfig, ZelleConfig, StripeConfig, TransaccionPasarela
from .serializers import (
    BancoSerializer,
    MetodoPagoConfigSerializer,
    PagoMovilConfigSerializer,
    ZelleConfigSerializer,
    StripeConfigSerializer,
    TransaccionPasarelaSerializer,
)


class BancoViewSet(viewsets.ModelViewSet):
    """CRUD de entidades bancarias -- ver docstring de `Banco`."""
    queryset = Banco.objects.filter(activo=True)
    serializer_class = BancoSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == 'destroy':
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Baja lógica: un banco ya referenciado por un método de pago no
        # debe desaparecer de golpe (rompería el historial de Cobros).
        instance.activo = False
        instance.save(update_fields=['activo'])


class MetodoPagoConfigViewSet(viewsets.ModelViewSet):
    """
    Permite a los administradores del tenant gestionar los métodos de pago disponibles.
    """
    queryset = MetodoPagoConfig.objects.all()
    serializer_class = MetodoPagoConfigSerializer
    permission_classes = [IsTenantAdmin]

class PagoMovilConfigViewSet(viewsets.ModelViewSet):
    queryset = PagoMovilConfig.objects.all()
    serializer_class = PagoMovilConfigSerializer
    permission_classes = [IsTenantAdmin]

class ZelleConfigViewSet(viewsets.ModelViewSet):
    queryset = ZelleConfig.objects.all()
    serializer_class = ZelleConfigSerializer
    permission_classes = [IsTenantAdmin]

class StripeConfigViewSet(viewsets.ModelViewSet):
    queryset = StripeConfig.objects.all()
    serializer_class = StripeConfigSerializer
    permission_classes = [IsTenantAdmin]

class TransaccionPasarelaViewSet(viewsets.ModelViewSet):
    """
    Permite a los administradores del tenant ver y confirmar/rechazar las
    transacciones de pasarela (ej. verificar un pago móvil reportado desde
    el catálogo público antes de marcar el pedido como pagado).
    """
    queryset = TransaccionPasarela.objects.select_related('metodo_pago', 'factura').order_by('-fecha_creacion')
    serializer_class = TransaccionPasarelaSerializer
    permission_classes = [IsTenantAdmin]
    filterset_fields = ['estado', 'factura']