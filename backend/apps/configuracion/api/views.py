"""
Vistas de la app de configuración.

Incluye la configuración de empresa, IVA, tipos de documento fiscal, módulos
de multi-moneda (Moneda, TasaCambio) y un endpoint para consultar la
estrategia fiscal activa (SENIAT / DIAN / SUNAT) del tenant.
"""
from __future__ import annotations

from django.db import transaction

from rest_framework import generics, permissions, viewsets
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from apps.core.response import standard_response, error_response, error_response_from_dict
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle

from ..models import ConfiguracionCorrelativo, ConfiguracionEmpresa, Configuracioniva, Moneda, TasaCambio, Tipodocumentofiscal
from ..services.conversion_service import obtener_tasas_actuales, invalidar_tasas_cambio
from ..services.bcv_service import asegurar_tasa_bcv_del_dia, BcvApiError
from ..services.pin_service import verificar_pin
from ..core.config_service import obtener_tax_strategy_info, obtener_pais_tenant
from .serializers import (
    ConfiguracionEmpresaSerializer,
    IvaSerializer,
    MonedaSerializer,
    TasaCambioSerializer,
    TipoDocumentoSerializer,
)
# Los serializers de correlativo viven en `facturacion` (ver ese módulo):
# el modelo `ConfiguracionCorrelativo` es de `configuracion`, pero el
# correlativo es un concepto de facturación -- se dejó así en el código
# existente y esta vista sigue esa misma convención en vez de moverlos.
from apps.facturacion.api.serializers import (
    ConfiguracionCorrelativoReadSerializer,
    ConfiguracionCorrelativoWriteSerializer,
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


class RequierePinEliminarView(APIView):
    """
    Expone SOLO si el tenant exige PIN para eliminar renglones -- nunca el
    PIN/hash en sí. Cualquier usuario logueado (un cajero, no solo el admin)
    necesita saber esto para decidir si pedirle el PIN a un encargado antes
    de dejarlo eliminar algo (ver `apps.configuracion.services.pin_service`).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        config, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        return standard_response(data={"requiere_pin_eliminar": config.requiere_pin_eliminar})


class VerificarPinView(APIView):
    """Verifica un PIN ingresado -- nunca revela el PIN real, solo si coincide."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'pin_autorizacion'

    def post(self, request):
        pin = str(request.data.get('pin') or '')
        return standard_response(data={"valido": verificar_pin(pin)})


class ConfiguracionCorrelativoView(APIView):
    """
    Consulta y ajuste de la numeración de facturas (correlativo/N° de control).

    No todas las empresas empiezan a facturar desde 001 (ej. migran desde
    otro sistema) -- este endpoint permite fijar ese punto de partida.

    Protegido con la contraseña del usuario (no solo el permiso de admin):
    un error aquí puede hacer que dos facturas terminen con el mismo
    correlativo, lo cual es un problema fiscal serio, así que se exige una
    confirmación explícita. Por la misma razón, una vez que el tenant ya
    emitió al menos una factura (`current_number > 0`) el número solo puede
    AVANZAR, nunca retroceder -- retroceder reabriría números ya usados.
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        config, _ = ConfiguracionCorrelativo.objects.get_or_create(pk=1)
        return standard_response(data=ConfiguracionCorrelativoReadSerializer(config).data)

    @transaction.atomic
    def patch(self, request):
        # Bloquea la fila mientras se valida y guarda: evita que una factura
        # se esté emitiendo (incrementando el contador) al mismo tiempo que
        # se reconfigura el punto de partida.
        config = ConfiguracionCorrelativo.objects.select_for_update().get_or_create(pk=1)[0]

        serializer = ConfiguracionCorrelativoWriteSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response_from_dict(serializer.errors)

        password = serializer.validated_data.pop('password', None)
        if not password or not request.user.check_password(password):
            return error_response(
                [{"code": "invalid_password", "detail": "Contraseña incorrecta.", "field": "password"}],
                status_code=403,
            )

        nuevo_numero = serializer.validated_data.get('current_number')
        if nuevo_numero is not None and config.current_number > 0 and nuevo_numero < config.current_number:
            return error_response([{
                "code": "correlativo_retroceso",
                "detail": (
                    f"No puedes bajar el número por debajo de {config.current_number}: "
                    "ya se emitieron facturas con esa numeración. Solo puedes avanzarlo."
                ),
                "field": "current_number",
            }])

        for field, value in serializer.validated_data.items():
            setattr(config, field, value)
        config.save()

        return standard_response(data=ConfiguracionCorrelativoReadSerializer(config).data)


class IvaViewSet(viewsets.ModelViewSet):
    """Administra las configuraciones de IVA."""

    queryset = Configuracioniva.objects.all().order_by('-activo', 'porcentaje_iva', 'id')
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
        invalidar_tasas_cambio()

    def perform_update(self, serializer):
        moneda = serializer.save()
        if moneda.es_predeterminada:
            Moneda.objects.exclude(pk=moneda.pk).update(es_predeterminada=False)
        invalidar_tasas_cambio()

    def perform_destroy(self, instance):
        instance.delete()
        invalidar_tasas_cambio()


class TasaCambioViewSet(viewsets.ModelViewSet):
    """
    Administra el historial de tasas de cambio.

    `get_tasa_vigente()` cachea la tasa en Redis hasta 15 minutos (ver
    `conversion_service.py`) -- sin invalidar aquí, una tasa recién creada
    (desde esta pantalla o desde el POS) podía tardar hasta 15 minutos en
    aplicarse de verdad a una venta, algo crítico cuando la tasa se
    actualiza a diario por la volatilidad cambiaria.
    """

    queryset = TasaCambio.objects.select_related("moneda").all()
    serializer_class = TasaCambioSerializer
    permission_classes = [IsTenantAdmin]

    def perform_create(self, serializer):
        serializer.save()
        invalidar_tasas_cambio()

    def perform_update(self, serializer):
        serializer.save()
        invalidar_tasas_cambio()

    def perform_destroy(self, instance):
        instance.delete()
        invalidar_tasas_cambio()


class ActualizarTasaBcvView(APIView):
    """
    Fuerza una consulta inmediata a DolarAPI para traer la tasa oficial del
    BCV -- sin esperar a que el chequeo automático (ligado al primer uso del
    día en `get_tasa_vigente`) la traiga sola. Botón de refresco manual.
    """

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        try:
            tasa = asegurar_tasa_bcv_del_dia(forzar=True)
        except BcvApiError as exc:
            return error_response([{"code": "bcv_api_error", "detail": str(exc), "field": None}])
        return standard_response(data=TasaCambioSerializer(tasa).data, status_code=201)


class TaxStrategyView(generics.GenericAPIView):
    """
    Expone la estrategia fiscal activa y las tasas aplicables.

    Útil para que el frontend renderice dinámicamente los impuestos y
    retenciones según el país configurado del tenant (Venezuela/Colombia/Perú).
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        # El país se puede forzar por query param (ej. para previsualizar otra
        # jurisdicción); por defecto usa el país configurado del tenant.
        country = request.query_params.get("country") or obtener_pais_tenant()
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
