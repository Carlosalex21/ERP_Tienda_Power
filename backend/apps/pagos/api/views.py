from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from ..models import MetodoPagoConfig, PagoMovilConfig, ZelleConfig, TransaccionPasarela
from .serializers import MetodoPagoConfigSerializer, PagoMovilConfigSerializer, ZelleConfigSerializer, TransaccionPasarelaSerializer

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

class TransaccionPasarelaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Permite a los administradores del tenant ver las transacciones de pasarela.
    """
    queryset = TransaccionPasarela.objects.all()
    serializer_class = TransaccionPasarelaSerializer
    permission_classes = [IsTenantAdmin]