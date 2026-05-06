from rest_framework import viewsets, permissions
from apps.configuracion.models import Configuracioniva, Tipodocumentofiscal
from apps.configuracion.api.serializers import ConfiguracionivaSerializer, TipodocumentofiscalSerializer

class IvaViewSet(viewsets.ModelViewSet):
    queryset = Configuracioniva.objects.filter(activo=True)
    serializer_class = ConfiguracionivaSerializer
    permission_classes = [permissions.IsAdminUser]

class TipoDocumentoViewSet(viewsets.ModelViewSet):
    queryset = Tipodocumentofiscal.objects.filter(activo=True)
    serializer_class = TipodocumentofiscalSerializer
    permission_classes = [permissions.IsAdminUser]