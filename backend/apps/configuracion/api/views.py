from rest_framework import generics, permissions, viewsets
from .serializers import ConfiguracionEmpresaSerializer, IvaSerializer, TipoDocumentoSerializer
from ..models import ConfiguracionEmpresa, Configuracioniva, Tipodocumentofiscal
from apps.core.permissions import IsTenantAdmin

class ConfiguracionEmpresaView(generics.RetrieveUpdateAPIView):
    """
    Vista para ver y actualizar la configuración de la empresa del tenant actual.
    Siempre opera sobre el objeto con pk=1.
    """
    serializer_class = ConfiguracionEmpresaSerializer
    permission_classes = [IsTenantAdmin]

    def get_object(self):
        # get_or_create asegura que la configuración siempre exista.
        obj, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        return obj

class IvaViewSet(viewsets.ModelViewSet):
    """Administra las configuraciones de IVA."""
    queryset = Configuracioniva.objects.all()
    serializer_class = IvaSerializer
    permission_classes = [IsTenantAdmin]

class TipoDocumentoViewSet(viewsets.ModelViewSet):
    """Administra los tipos de documentos fiscales."""
    queryset = Tipodocumentofiscal.objects.all()
    serializer_class = TipoDocumentoSerializer
    permission_classes = [IsTenantAdmin]