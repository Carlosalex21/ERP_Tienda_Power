"""
Vistas de la app de configuración.

Incluye la configuración de empresa, IVA, tipos de documento fiscal, módulos
de multi-moneda (Moneda, TasaCambio) y un endpoint para consultar la
estrategia fiscal activa (SENIAT / DIAN / SUNAT) del tenant.
"""
from __future__ import annotations

from rest_framework import generics, permissions, viewsets
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from apps.core.response import standard_response

from ..models import ConfiguracionEmpresa, Configuracioniva, Moneda, TasaCambio, Tipodocumentofiscal
from ..services.conversion_service import obtener_tasas_actuales
from ..core.config_service import obtener_tax_strategy_info
from .serializers import (
    ConfiguracionEmpresaSerializer,
    IvaSerializer,
    MonedaSerializer,
    TasaCambioSerializer,
    TipoDocumentoSerializer,
)


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


class MonedaViewSet(viewsets.ModelViewSet):
    """
    Administra las monedas del tenant.

    Solo puede existir una moneda con ``es_predeterminada=True``.
    """

    queryset = Moneda.objects.all()
    serializer_class = MonedaSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None  # Las monedas son pocas; no paginar.

    def perform_create(self, serializer):
        moneda = serializer.save()
        if moneda.es_predeterminada:
            Moneda.objects.exclude(pk=moneda.pk).update(es_predeterminada=False)

    def perform_update(self, serializer):
        moneda = serializer.save()
        if moneda.es_predeterminada:
            Moneda.objects.exclude(pk=moneda.pk).update(es_predeterminada=False)


class TasaCambioViewSet(viewsets.ModelViewSet):
    """Administra el historial de tasas de cambio."""

    queryset = TasaCambio.objects.select_related("moneda").all()
    serializer_class = TasaCambioSerializer
    permission_classes = [IsTenantAdmin]


class TaxStrategyView(generics.GenericAPIView):
    """
    Expone la estrategia fiscal activa y las tasas aplicables.

    Útil para que el frontend renderice dinámicamente los impuestos y
    retenciones según el país configurado del tenant (Venezuela/Colombia/Perú).
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        # El país se puede configurar por query param; por defecto Venezuela.
        country = request.query_params.get("country", "VE")
        # Lectura cacheada en Redis por país (ver config_service).
        data = obtener_tax_strategy_info(country)
        return standard_response(data=data)


@extend_schema(
    tags=["configuracion"],
    summary="Tasas de cambio vigentes de todas las monedas activas.",
    description=(
        "Devuelve un mapa con las tasas vigentes de cada moneda activa del "
        "tenant. La moneda base se reporta con tasa 1.000000. Las monedas sin "
        "tasa vigente se reportan con tasa null."
    ),
)
class TasaCambioActualView(APIView):
    """Expone las tasas de cambio vigentes (cacheadas) de todas las monedas."""

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        """
        Devuelve las tasas vigentes de todas las monedas activas.

        Args:
            request: Petición HTTP (no requiere parámetros).

        Returns:
            Response: Estructura ``{data: {codigo: {codigo, nombre, simbolo,
            tasa, es_base}}, meta, errors}``.
        """
        tasas = obtener_tasas_actuales()
        return standard_response(data=tasas)
