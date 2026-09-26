from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor

from ..models import Cotizacion, Oportunidad
from ..services import (
    crear_oportunidad, actualizar_etapa_oportunidad,
    crear_cotizacion, cambiar_estado_cotizacion, convertir_cotizacion_a_venta,
    CrmError,
)
from .serializers import (
    OportunidadSerializer, CambiarEtapaOportunidadSerializer,
    CotizacionSerializer, CrearCotizacionSerializer, CambiarEstadoCotizacionSerializer,
    ConvertirCotizacionSerializer, CotizacionPublicaSerializer,
)


class OportunidadViewSet(viewsets.ModelViewSet):
    """Pipeline de oportunidades comerciales -- se edita libre (título, etapa, seguimiento) salvo la acción `cambiar-etapa`, que es la vía recomendada para mover el pipeline."""
    queryset = Oportunidad.objects.select_related('cliente', 'usuario_asignado', 'departamento')
    serializer_class = OportunidadSerializer
    permission_classes = [IsAdminOrVendedor]

    def get_queryset(self):
        qs = super().get_queryset()
        etapa = self.request.query_params.get('etapa')
        if etapa:
            qs = qs.filter(etapa=etapa)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = OportunidadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            oportunidad = crear_oportunidad(
                titulo=data['titulo'], usuario=request.user,
                cliente_id=data.get('cliente') and data['cliente'].id,
                nombre_prospecto=data.get('nombre_prospecto', ''),
                telefono_prospecto=data.get('telefono_prospecto', ''),
                valor_estimado=data.get('valor_estimado'),
                fecha_cierre_estimada=data.get('fecha_cierre_estimada'),
                proximo_seguimiento=data.get('proximo_seguimiento'),
                usuario_asignado_id=data.get('usuario_asignado') and data['usuario_asignado'].id,
                departamento_id=data.get('departamento') and data['departamento'].id,
                observaciones=data.get('observaciones', ''),
            )
        except CrmError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(oportunidad).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cambiar-etapa')
    def cambiar_etapa(self, request, pk=None):
        oportunidad = self.get_object()
        serializer = CambiarEtapaOportunidadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            actualizar_etapa_oportunidad(
                oportunidad, serializer.validated_data['etapa'], serializer.validated_data.get('motivo_perdida', ''),
            )
        except CrmError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(oportunidad).data)


class CotizacionViewSet(viewsets.ModelViewSet):
    """Cotizaciones -- de solo lectura + creación (`create` construye cabecera y líneas de una vez); cambios de estado y conversión van por acciones dedicadas."""
    queryset = Cotizacion.objects.select_related('cliente', 'moneda', 'usuario', 'oportunidad').prefetch_related('detalles__producto', 'detalles__variante')
    serializer_class = CotizacionSerializer
    permission_classes = [IsAdminOrVendedor]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        cliente_id = self.request.query_params.get('cliente')
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = CrearCotizacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            cotizacion = crear_cotizacion(
                usuario=request.user,
                cliente_id=data.get('cliente_id'),
                nombre_prospecto=data.get('nombre_prospecto', ''),
                telefono_prospecto=data.get('telefono_prospecto', ''),
                oportunidad_id=data.get('oportunidad_id'),
                moneda_id=data.get('moneda_id'),
                fecha_vencimiento=data.get('fecha_vencimiento'),
                observaciones=data.get('observaciones', ''),
                detalles_data=[
                    {
                        'producto_id': d['producto_id'], 'variante_id': d.get('variante_id'),
                        'cantidad': d['cantidad'], 'precio_unitario': d['precio_unitario'],
                    }
                    for d in data['detalles']
                ],
            )
        except CrmError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cotizacion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cambiar-estado')
    def cambiar_estado(self, request, pk=None):
        cotizacion = self.get_object()
        serializer = CambiarEstadoCotizacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cambiar_estado_cotizacion(cotizacion, serializer.validated_data['estado'])
        except CrmError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(cotizacion).data)

    @action(detail=True, methods=['post'])
    def convertir(self, request, pk=None):
        cotizacion = self.get_object()
        serializer = ConvertirCotizacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            factura = convertir_cotizacion_a_venta(
                cotizacion, usuario=request.user,
                condicion_pago=serializer.validated_data['condicion_pago'],
                almacen_id=serializer.validated_data.get('almacen_id'),
            )
        except CrmError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        cotizacion.refresh_from_db()
        return Response({
            "cotizacion": self.get_serializer(cotizacion).data,
            "factura_id": factura.id,
        })


class CotizacionPublicaView(APIView):
    """Lo que ve el cliente al abrir el link/QR de su cotización -- sin login, sin datos internos."""
    permission_classes = [AllowAny]

    def get(self, request, token):
        cotizacion = Cotizacion.objects.filter(token_publico=token).prefetch_related('detalles__producto').first()
        if cotizacion is None:
            return Response({"error": "Cotización no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CotizacionPublicaSerializer(cotizacion).data)
