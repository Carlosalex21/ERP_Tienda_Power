"""
Vistas de turno de caja (apertura/cierre por usuario) y del reporte de
Cobros (pagos registrados, agrupables por banco/método para cuadrar contra
el estado de cuenta real al final del día).
"""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.response import standard_response
from apps.facturacion.models import CajaSesion, CajaSesionMonto, Transaccionpago
from apps.facturacion.services.caja_service import (
    CajaServiceError,
    abrir_caja_service,
    cerrar_caja_service,
    obtener_caja_activa,
)


class CajaSesionMontoSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.CharField(source="moneda.codigo", read_only=True)
    moneda_simbolo = serializers.CharField(source="moneda.simbolo", read_only=True)
    diferencia = serializers.SerializerMethodField()

    class Meta:
        model = CajaSesionMonto
        fields = (
            "id", "moneda", "moneda_codigo", "moneda_simbolo",
            "monto_apertura", "monto_cierre_esperado", "monto_cierre_declarado", "diferencia",
        )

    def get_diferencia(self, obj):
        d = obj.diferencia
        return str(d) if d is not None else None


class CajaSesionSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    montos = CajaSesionMontoSerializer(many=True, read_only=True)

    class Meta:
        model = CajaSesion
        fields = ("id", "usuario", "usuario_nombre", "fecha_apertura", "fecha_cierre", "observaciones_cierre", "activo", "montos")

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username


class CajaActualView(APIView):
    """Turno de caja abierto del usuario actual (o null si no tiene uno)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sesion = obtener_caja_activa(request.user)
        return standard_response(data=CajaSesionSerializer(sesion).data if sesion else None)


class AbrirCajaView(APIView):
    """Abre un turno de caja para el usuario actual."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Abrir turno de caja")
    def post(self, request):
        montos = request.data.get("montos_apertura", {}) or {}
        try:
            sesion = abrir_caja_service(request.user, montos)
        except CajaServiceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return standard_response(data=CajaSesionSerializer(sesion).data, status_code=status.HTTP_201_CREATED)


class CerrarCajaView(APIView):
    """Cierra el turno de caja abierto del usuario actual."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Cerrar turno de caja")
    def post(self, request):
        montos = request.data.get("montos_declarados", {}) or {}
        observaciones = request.data.get("observaciones", "")
        try:
            sesion = cerrar_caja_service(request.user, montos, observaciones)
        except CajaServiceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return standard_response(data=CajaSesionSerializer(sesion).data)


class HistorialCajaView(APIView):
    """Lista los turnos de caja pasados (todos los usuarios) -- para que un admin audite cierres anteriores."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = CajaSesion.objects.select_related('usuario').prefetch_related('montos__moneda').order_by('-fecha_apertura')[:100]
        return standard_response(data=CajaSesionSerializer(qs, many=True).data)


class CobroSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source="metodo_pago.nombre", read_only=True, default=None)
    banco_nombre = serializers.CharField(source="metodo_pago.banco.nombre", read_only=True, default=None)
    factura_correlativo = serializers.CharField(source="factura.correlativo", read_only=True, default=None)
    moneda_codigo = serializers.CharField(source="factura.moneda.codigo", read_only=True, default=None)
    cajero_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Transaccionpago
        fields = (
            "id", "factura", "factura_correlativo", "monto", "monto_recibido", "vuelto",
            "metodo_pago", "metodo_pago_nombre", "banco_nombre", "moneda_codigo",
            "referencia", "fecha", "estado", "cajero_nombre",
        )

    def get_cajero_nombre(self, obj):
        usuario = obj.caja_sesion.usuario if obj.caja_sesion else None
        if not usuario:
            return None
        return usuario.get_full_name() or usuario.username


class CobrosReportView(APIView):
    """
    Reporte de Cobros: cada pago registrado (`Transaccionpago`), con su
    banco (a través del método de pago) y quién lo cobró -- para cuadrar al
    final del día/turno contra el estado de cuenta real de cada banco.

    Filtros opcionales: ``fecha_desde``, ``fecha_hasta`` (YYYY-MM-DD),
    ``banco_id``, ``metodo_pago_id``.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Transaccionpago.objects.filter(activo=True, estado="exitoso").select_related(
            'factura', 'factura__moneda', 'metodo_pago', 'metodo_pago__banco', 'caja_sesion__usuario',
        ).order_by('-fecha')

        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        banco_id = request.query_params.get('banco_id')
        metodo_pago_id = request.query_params.get('metodo_pago_id')

        if fecha_desde:
            qs = qs.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__date__lte=fecha_hasta)
        if banco_id:
            qs = qs.filter(metodo_pago__banco_id=banco_id)
        if metodo_pago_id:
            qs = qs.filter(metodo_pago_id=metodo_pago_id)

        return standard_response(data=CobroSerializer(qs[:500], many=True).data)
