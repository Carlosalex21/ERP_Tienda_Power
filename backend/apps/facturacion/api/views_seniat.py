"""
ViewSets para los documentos fiscales SENIAT:

* Notas de crédito y débito.
* Libros de compras y ventas.
* Comprobantes de retención (ISLR / IVA).

Cada ViewSet delega la **lógica de negocio** a los servicios de la app
(``notas_service``, ``libros_service``, ``retencion_service``) para mantener
una única fuente de verdad en el cálculo de montos y numeración, y para
garantizar el registro automático en el Libro de Compra/Venta.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.core.permissions import IsAdminOrVendedor, IsTenantAdmin
from apps.core.response import error_response, standard_response

from apps.facturacion.models import LibroCompraVenta, NotaCredito, NotaDebito, Retencion
from apps.facturacion.api.serializers import (
    LibroCompraVentaSerializer,
    NotaCreditoSerializer,
    NotaDebitoSerializer,
    RetencionSerializer,
)
from apps.facturacion.services.notas_service import (
    NotaServiceError,
    crear_nota_credito,
    crear_nota_debito,
)
from apps.facturacion.services.retencion_service import (
    RetencionServiceError,
    crear_comprobante_retencion,
)


@extend_schema(tags=["facturacion"])
class NotaCreditoViewSet(viewsets.ModelViewSet):
    """Gestiona las notas de crédito (SENIAT)."""

    queryset = NotaCredito.objects.select_related("factura").filter(activo=True)
    serializer_class = NotaCreditoSerializer

    def get_permissions(self):
        if self.action == "destroy":
            self.permission_classes = [IsTenantAdmin]
        else:
            self.permission_classes = [IsAdminOrVendedor]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Baja lógica, nunca borrado físico: es un documento fiscal emitido
        # (tiene numero_nota/numero_control asignados desde que se crea) --
        # desaparecerlo de verdad rompería la trazabilidad ante el SENIAT.
        instance.activo = False
        instance.save(update_fields=["activo"])

    def perform_create(self, serializer):
        """
        Crea la nota de crédito usando la lógica de negocio del servicio.

        El serializer valida ``factura``, ``monto`` y ``motivo``; el servicio
        genera el número de control, calcula la distribución proporcional de
        base/IVA/retención y registra la línea en el Libro de Venta.
        """
        data = serializer.validated_data
        factura = data["factura"]
        monto = data["monto"]
        motivo = data["motivo"]
        nota = crear_nota_credito(
            factura_id=factura.id,
            monto=monto,
            motivo=motivo,
        )
        serializer.instance = nota

    def create(self, request, *args, **kwargs):
        """Crea la nota de crédito y envuelve la respuesta en el estándar."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except NotaServiceError as exc:
            return error_response(
                [{"code": "nota_credito_error", "detail": str(exc), "field": None}],
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        headers = self.get_success_headers(serializer.data)
        return standard_response(
            data=serializer.data,
            status_code=status.HTTP_201_CREATED,
            meta={"headers": headers},
        )


@extend_schema(tags=["facturacion"])
class NotaDebitoViewSet(viewsets.ModelViewSet):
    """Gestiona las notas de débito (SENIAT)."""

    queryset = NotaDebito.objects.select_related("factura").filter(activo=True)
    serializer_class = NotaDebitoSerializer

    def get_permissions(self):
        if self.action == "destroy":
            self.permission_classes = [IsTenantAdmin]
        else:
            self.permission_classes = [IsAdminOrVendedor]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Baja lógica -- ver el mismo comentario en NotaCreditoViewSet.
        instance.activo = False
        instance.save(update_fields=["activo"])

    def perform_create(self, serializer):
        """Crea la nota de débito usando la lógica del servicio."""
        data = serializer.validated_data
        factura = data["factura"]
        monto = data["monto"]
        motivo = data["motivo"]
        nota = crear_nota_debito(
            factura_id=factura.id,
            monto=monto,
            motivo=motivo,
        )
        serializer.instance = nota

    def create(self, request, *args, **kwargs):
        """Crea la nota de débito y envuelve la respuesta en el estándar."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except NotaServiceError as exc:
            return error_response(
                [{"code": "nota_debito_error", "detail": str(exc), "field": None}],
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        headers = self.get_success_headers(serializer.data)
        return standard_response(
            data=serializer.data,
            status_code=status.HTTP_201_CREATED,
            meta={"headers": headers},
        )


@extend_schema(tags=["facturacion"])
class LibroCompraVentaViewSet(viewsets.ModelViewSet):
    """Gestiona el libro de compras y ventas (SENIAT)."""

    queryset = LibroCompraVenta.objects.filter(activo=True)
    serializer_class = LibroCompraVentaSerializer
    filterset_fields = ("tipo_libro", "fecha_operacion")

    def get_permissions(self):
        if self.action in ("destroy", "create", "update", "partial_update"):
            self.permission_classes = [IsTenantAdmin]
        else:
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="tipo_libro",
                type=str,
                enum=["compra", "venta"],
                description="Filtra por libro de compra o de venta.",
            ),
            OpenApiParameter(
                name="fecha_desde",
                type=OpenApiTypes.DATE,
                description="Fecha de inicio del rango (YYYY-MM-DD).",
            ),
            OpenApiParameter(
                name="fecha_hasta",
                type=OpenApiTypes.DATE,
                description="Fecha de fin del rango (YYYY-MM-DD).",
            ),
        ],
        responses={200: LibroCompraVentaSerializer(many=True)},
        summary="Reporte del Libro de Compra/Venta por rango de fechas.",
    )
    @action(detail=False, methods=["get"])
    def reportes(self, request):
        """
        Devuelve las líneas del libro filtradas por tipo y rango de fechas.

        Args:
            request: Petición HTTP con query params opcionales
                ``tipo_libro``, ``fecha_desde`` y ``fecha_hasta``.
        """
        qs = self.get_queryset()
        tipo_libro = request.query_params.get("tipo_libro")
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")

        if tipo_libro:
            qs = qs.filter(tipo_libro=tipo_libro)
        if fecha_desde:
            qs = qs.filter(fecha_operacion__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_operacion__lte=fecha_hasta)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(qs, many=True)
        return standard_response(data=serializer.data)


@extend_schema(tags=["facturacion"])
class RetencionViewSet(viewsets.ModelViewSet):
    """Gestiona los comprobantes de retención (SENIAT)."""

    queryset = Retencion.objects.select_related("factura", "proveedor").filter(activo=True)
    serializer_class = RetencionSerializer

    def get_permissions(self):
        if self.action == "destroy":
            self.permission_classes = [IsTenantAdmin]
        else:
            self.permission_classes = [IsTenantAdmin]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # Baja lógica -- ver el mismo comentario en NotaCreditoViewSet.
        instance.activo = False
        instance.save(update_fields=["activo"])

    def perform_create(self, serializer):
        """
        Crea el comprobante de retención con el monto autocalculado.

        El serializer valida ``factura``/``proveedor``, ``tipo_retencion``,
        ``porcentaje`` y ``base``; el servicio calcula el monto y genera el
        número de comprobante.
        """
        data = serializer.validated_data
        comprobante = crear_comprobante_retencion(
            factura=data.get("factura"),
            proveedor=data.get("proveedor"),
            tipo_retencion=data["tipo_retencion"],
            porcentaje=data["porcentaje"],
            base=data["base"],
            periodo_imposicion=data.get("periodo_imposicion"),
        )
        serializer.instance = comprobante

    def create(self, request, *args, **kwargs):
        """Crea la retención y envuelve la respuesta en el estándar."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except RetencionServiceError as exc:
            return error_response(
                [{"code": "retencion_error", "detail": str(exc), "field": None}],
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        headers = self.get_success_headers(serializer.data)
        return standard_response(
            data=serializer.data,
            status_code=status.HTTP_201_CREATED,
            meta={"headers": headers},
        )