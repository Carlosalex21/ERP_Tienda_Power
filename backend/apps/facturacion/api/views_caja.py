"""
Vistas de turno de caja (apertura/cierre por usuario) y del reporte de
Cobros (pagos registrados, agrupables por banco/método para cuadrar contra
el estado de cuenta real al final del día).
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.permissions import IsTenantAdmin
from apps.core.response import standard_response
from apps.facturacion.models import CajaSesion, CajaSesionMonto, MovimientoCaja, Transaccionpago
from apps.facturacion.services.caja_service import (
    CajaServiceError,
    abrir_caja_service,
    cerrar_caja_service,
    obtener_caja_activa,
    previsualizar_cierre_caja,
    registrar_movimiento_caja,
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


class PrevisualizarCierreCajaView(APIView):
    """
    Calcula el cuadre del turno abierto (por moneda: apertura, ventas en
    efectivo que lo componen, y el total esperado) SIN cerrarlo -- para que
    el cajero vea de dónde sale la cifra antes de confirmar (ver
    `previsualizar_cierre_caja`).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            data = previsualizar_cierre_caja(request.user)
        except CajaServiceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return standard_response(data=data)


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
    # El docstring ya decía "para que un admin audite" pero el permiso real
    # era `IsAuthenticated`: cualquier empleado podía ver los cierres de
    # caja (y sus diferencias de efectivo) de TODOS los demás.
    permission_classes = [IsTenantAdmin]

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
    # Reporte financiero cruzando todos los cajeros/bancos del negocio --
    # antes cualquier empleado autenticado podía verlo, igual que
    # `HistorialCajaView`.
    permission_classes = [IsTenantAdmin]

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


class MovimientoCajaSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.CharField(source="moneda.codigo", read_only=True)
    moneda_simbolo = serializers.CharField(source="moneda.simbolo", read_only=True, default=None)
    banco_nombre = serializers.CharField(source="banco.nombre", read_only=True, default=None)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoCaja
        fields = (
            "id", "tipo", "caja_sesion", "banco", "banco_nombre", "moneda", "moneda_codigo",
            "moneda_simbolo", "monto", "concepto", "usuario", "usuario_nombre", "fecha",
        )
        read_only_fields = ("usuario", "fecha")

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username


class MovimientoCajaView(APIView):
    """
    Ingresos/egresos manuales de caja (ej. "llevé el efectivo contado al
    banco") -- cualquier empleado logueado puede registrar uno (lo hace el
    mismo cajero al cerrar turno); solo un admin puede LISTAR el histórico
    completo de todos, ver `IsTenantAdmin` en el GET.
    """

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsTenantAdmin()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = MovimientoCaja.objects.select_related('moneda', 'banco', 'usuario').order_by('-fecha')
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')
        if fecha_desde:
            qs = qs.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__date__lte=fecha_hasta)
        return standard_response(data=MovimientoCajaSerializer(qs[:500], many=True).data)

    @extend_schema(summary="Registrar un ingreso/egreso manual de caja")
    def post(self, request):
        data = request.data
        try:
            movimiento = registrar_movimiento_caja(
                usuario=request.user,
                tipo=data.get("tipo"),
                moneda_id=data.get("moneda"),
                monto=data.get("monto"),
                concepto=data.get("concepto", ""),
                banco_id=data.get("banco"),
                caja_sesion_id=data.get("caja_sesion"),
            )
        except CajaServiceError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return standard_response(data=MovimientoCajaSerializer(movimiento).data, status_code=status.HTTP_201_CREATED)


class ReporteCajaBancosView(APIView):
    """
    Reporte de caja y bancos, agrupado por día: combina los cobros
    (`Transaccionpago`) y los movimientos manuales (`MovimientoCaja`,
    ingresos/egresos) en una sola línea de tiempo por fecha, con el saldo
    neto de cada día -- lo que junta "todos los movimientos que hubo hasta
    el cierre para llegar a esa cifra" en un solo lugar, en vez de tener que
    cruzar el reporte de Cobros con las observaciones sueltas de cada cierre
    de caja.

    Filtros opcionales: ``fecha_desde``, ``fecha_hasta`` (YYYY-MM-DD).
    """
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        fecha_desde = request.query_params.get('fecha_desde')
        fecha_hasta = request.query_params.get('fecha_hasta')

        cobros = Transaccionpago.objects.filter(activo=True, estado="exitoso").select_related(
            'factura', 'factura__moneda', 'metodo_pago', 'metodo_pago__banco', 'caja_sesion__usuario',
        )
        movimientos = MovimientoCaja.objects.select_related('moneda', 'banco', 'usuario')
        if fecha_desde:
            cobros = cobros.filter(fecha__date__gte=fecha_desde)
            movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            cobros = cobros.filter(fecha__date__lte=fecha_hasta)
            movimientos = movimientos.filter(fecha__date__lte=fecha_hasta)

        dias: dict[str, dict] = {}

        def _dia(fecha):
            clave = fecha.date().isoformat()
            if clave not in dias:
                dias[clave] = {"fecha": clave, "cobros": [], "movimientos": [], "total_cobros": Decimal("0.00"), "total_ingresos": Decimal("0.00"), "total_egresos": Decimal("0.00")}
            return dias[clave]

        for t in cobros.order_by('fecha')[:2000]:
            if not t.fecha:
                continue
            d = _dia(t.fecha)
            d["cobros"].append(CobroSerializer(t).data)
            d["total_cobros"] += t.monto

        for m in movimientos.order_by('fecha')[:2000]:
            d = _dia(m.fecha)
            d["movimientos"].append(MovimientoCajaSerializer(m).data)
            if m.tipo == "ingreso":
                d["total_ingresos"] += m.monto
            else:
                d["total_egresos"] += m.monto

        resultado = []
        for clave in sorted(dias.keys(), reverse=True):
            d = dias[clave]
            d["saldo_neto"] = d["total_cobros"] + d["total_ingresos"] - d["total_egresos"]
            resultado.append(d)

        return standard_response(data=resultado)
