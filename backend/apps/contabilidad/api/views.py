from datetime import date

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsTenantAdmin

from .. import exports
from ..models import EmpresaContable, CuentaContable, AsientoContable, AsientoPlantilla
from ..services import (
    crear_asiento_contable, anular_asiento_contable, seed_plan_cuentas_default,
    contabilizar_asiento_borrador, libro_mayor, balance_comprobacion, estados_financieros,
    AsientoContableError, facturar_honorarios_empresa, FacturarHonorariosError,
    cerrar_ejercicio, crear_plantilla_desde_asiento, conciliacion_bancaria, marcar_conciliado,
    obtener_o_crear_empresa_propia,
)
from .serializers import (
    EmpresaContableSerializer, CuentaContableSerializer, AsientoContableSerializer,
    CrearAsientoContableSerializer, FacturarHonorariosSerializer,
    AsientoPlantillaSerializer, CrearPlantillaDesdeAsientoSerializer,
    CerrarEjercicioSerializer, MarcarConciliadoSerializer,
)


class EmpresaContableViewSet(viewsets.ModelViewSet):
    queryset = EmpresaContable.objects.filter(activo=True).select_related('cliente')
    serializer_class = EmpresaContableSerializer
    permission_classes = [IsTenantAdmin]
    # Sin paginar -- este listado alimenta el selector de empresa que
    # aparece en TODAS las pantallas del módulo (necesita verlas todas para
    # poder elegir cualquiera, no solo las primeras 20 de la página 1).
    pagination_class = None

    def perform_create(self, serializer):
        empresa = serializer.save()
        # Sin esto, el contador abriría una empresa nueva y vería una
        # pantalla de "plan de cuentas" completamente vacía sin saber por
        # dónde empezar -- el esqueleto sirve de punto de partida, se puede
        # editar libremente después.
        seed_plan_cuentas_default(empresa)

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])

    @action(detail=True, methods=['post'], url_path='facturar-honorarios')
    def facturar_honorarios(self, request, pk=None):
        empresa = self.get_object()
        serializer = FacturarHonorariosSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            factura, asiento = facturar_honorarios_empresa(
                empresa=empresa,
                lineas=serializer.validated_data['lineas'],
                metodo_pago_id=serializer.validated_data['metodo_pago_id'],
                cuenta_cobro_id=serializer.validated_data['cuenta_cobro_id'],
                cuenta_ingreso_id=serializer.validated_data['cuenta_ingreso_id'],
                usuario=request.user,
                condicion_pago=serializer.validated_data['condicion_pago'],
                moneda_id=serializer.validated_data.get('moneda_id'),
            )
        except FacturarHonorariosError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "mensaje": "Honorarios facturados y cobrados.",
            "factura_id": factura.id,
            "correlativo": factura.correlativo,
            "asiento_id": asiento.id if asiento else None,
            "asiento_numero": asiento.numero if asiento else None,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cerrar-ejercicio')
    def cerrar_ejercicio_action(self, request, pk=None):
        empresa = self.get_object()
        serializer = CerrarEjercicioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asiento = cerrar_ejercicio(
                empresa=empresa,
                fecha_desde=serializer.validated_data['fecha_desde'],
                fecha_hasta=serializer.validated_data['fecha_hasta'],
                cuenta_patrimonio_id=serializer.validated_data['cuenta_patrimonio_id'],
                usuario=request.user,
            )
        except AsientoContableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AsientoContableSerializer(asiento).data, status=status.HTTP_201_CREATED)


class MiEmpresaContableView(APIView):
    """
    Resuelve (auto-creando si hace falta) la `EmpresaContable` propia del
    tenant -- para verticales que no son 'contador', esta es la única forma
    en que el frontend llega a "sus" libros sin tener que pasar antes por
    una pantalla de "crear empresa contable" que no tiene sentido para un
    negocio que no lleva contabilidad de terceros.
    """
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        from apps.configuracion.models import ConfiguracionEmpresa

        config = ConfiguracionEmpresa.objects.first()
        empresa = obtener_o_crear_empresa_propia(
            nombre=getattr(config, 'nombre_comercial', None),
            identificacion_fiscal=getattr(config, 'rif', None),
        )
        return Response(EmpresaContableSerializer(empresa).data)


class CuentaContableViewSet(viewsets.ModelViewSet):
    queryset = CuentaContable.objects.filter(activo=True).select_related('cuenta_padre')
    serializer_class = CuentaContableSerializer
    permission_classes = [IsTenantAdmin]
    # Sin paginar -- el plan de cuentas completo tiene que estar disponible
    # de una vez en el selector de "Nuevo Asiento": con el default de 20 por
    # página, un plan de cuentas real (fácilmente 30-100+ cuentas) dejaba
    # cuentas enteras imposibles de seleccionar para un asiento sin que
    # nada avisara que faltaban.
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])


class AsientoContableViewSet(viewsets.ModelViewSet):
    """
    Solo lectura + creación -- un asiento contabilizado no se edita línea
    por línea (rompería el historial), se anula y se crea uno nuevo. Ver
    `services.crear_asiento_contable` (única vía que valida partida doble).
    """
    queryset = AsientoContable.objects.select_related('empresa', 'usuario').prefetch_related('detalles__cuenta')
    serializer_class = AsientoContableSerializer
    permission_classes = [IsTenantAdmin]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def create(self, request, *args, **kwargs):
        empresa_id = request.data.get('empresa')
        empresa = EmpresaContable.objects.filter(pk=empresa_id, activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CrearAsientoContableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asiento = crear_asiento_contable(
                empresa=empresa,
                fecha=serializer.validated_data['fecha'],
                descripcion=serializer.validated_data['descripcion'],
                lineas=serializer.validated_data['lineas'],
                usuario=request.user,
                estado=serializer.validated_data['estado'],
            )
        except AsientoContableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(asiento).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        asiento = self.get_object()
        try:
            anular_asiento_contable(asiento)
        except AsientoContableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(asiento).data)

    @action(detail=True, methods=['post'])
    def contabilizar(self, request, pk=None):
        asiento = self.get_object()
        try:
            contabilizar_asiento_borrador(asiento)
        except AsientoContableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(asiento).data)

    @action(detail=True, methods=['post'], url_path='comprobante', parser_classes=[MultiPartParser, FormParser])
    def subir_comprobante(self, request, pk=None):
        asiento = self.get_object()
        archivo = request.FILES.get('comprobante')
        if not archivo:
            return Response({"error": "No se recibió ningún archivo."}, status=status.HTTP_400_BAD_REQUEST)
        asiento.comprobante = archivo
        asiento.save(update_fields=['comprobante'])
        return Response(self.get_serializer(asiento).data)

    @action(detail=True, methods=['post'], url_path='guardar-como-plantilla')
    def guardar_como_plantilla(self, request, pk=None):
        asiento = self.get_object()
        serializer = CrearPlantillaDesdeAsientoSerializer(data={**request.data, 'asiento_id': asiento.id})
        serializer.is_valid(raise_exception=True)
        plantilla = crear_plantilla_desde_asiento(asiento, serializer.validated_data['nombre'])
        return Response(AsientoPlantillaSerializer(plantilla).data, status=status.HTTP_201_CREATED)


class AsientoPlantillaViewSet(viewsets.ModelViewSet):
    queryset = AsientoPlantilla.objects.filter(activo=True).prefetch_related('lineas__cuenta')
    serializer_class = AsientoPlantillaSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = self.request.query_params.get('empresa')
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])


def _parse_fecha(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


class LibroMayorView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        cuenta = CuentaContable.objects.filter(pk=request.query_params.get('cuenta')).first()
        if empresa is None or cuenta is None or cuenta.empresa_id != empresa.id:
            return Response({"error": "Empresa o cuenta inválida."}, status=status.HTTP_400_BAD_REQUEST)
        data = libro_mayor(
            empresa, cuenta,
            fecha_desde=_parse_fecha(request.query_params.get('desde')),
            fecha_hasta=_parse_fecha(request.query_params.get('hasta')),
        )
        return Response(data)


class BalanceComprobacionView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        data = balance_comprobacion(
            empresa,
            fecha_desde=_parse_fecha(request.query_params.get('desde')),
            fecha_hasta=_parse_fecha(request.query_params.get('hasta')),
        )
        return Response(data)


class EstadosFinancierosView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        data = estados_financieros(
            empresa,
            fecha_desde=_parse_fecha(request.query_params.get('desde')),
            fecha_hasta=_parse_fecha(request.query_params.get('hasta')),
        )
        return Response(data)


class ConciliacionBancariaView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        cuenta = CuentaContable.objects.filter(pk=request.query_params.get('cuenta')).first()
        if empresa is None or cuenta is None or cuenta.empresa_id != empresa.id:
            return Response({"error": "Empresa o cuenta inválida."}, status=status.HTTP_400_BAD_REQUEST)
        data = conciliacion_bancaria(
            empresa, cuenta, fecha_hasta=_parse_fecha(request.query_params.get('hasta')),
        )
        return Response(data)

    def post(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.data.get('empresa'), activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = MarcarConciliadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            marcar_conciliado(
                detalle_id=serializer.validated_data['detalle_id'],
                empresa=empresa,
                conciliado=serializer.validated_data['conciliado'],
            )
        except AsientoContableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"mensaje": "Actualizado."})


def _formato_valido(request):
    formato = request.query_params.get('formato', 'pdf')
    return formato if formato in ('pdf', 'excel') else 'pdf'


class BalanceComprobacionExportView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        fecha_desde = _parse_fecha(request.query_params.get('desde'))
        fecha_hasta = _parse_fecha(request.query_params.get('hasta'))
        filas = balance_comprobacion(empresa, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        if _formato_valido(request) == 'excel':
            return exports.balance_comprobacion_excel(empresa, filas)
        return exports.balance_comprobacion_pdf(empresa, filas, fecha_desde, fecha_hasta, download=True)


class EstadosFinancierosExportView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        if empresa is None:
            return Response({"error": "Empresa contable no encontrada."}, status=status.HTTP_400_BAD_REQUEST)
        fecha_desde = _parse_fecha(request.query_params.get('desde'))
        fecha_hasta = _parse_fecha(request.query_params.get('hasta'))
        datos = estados_financieros(empresa, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        if _formato_valido(request) == 'excel':
            return exports.estados_financieros_excel(empresa, datos)
        return exports.estados_financieros_pdf(empresa, datos, fecha_desde, fecha_hasta, download=True)


class LibroMayorExportView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        empresa = EmpresaContable.objects.filter(pk=request.query_params.get('empresa'), activo=True).first()
        cuenta = CuentaContable.objects.filter(pk=request.query_params.get('cuenta')).first()
        if empresa is None or cuenta is None or cuenta.empresa_id != empresa.id:
            return Response({"error": "Empresa o cuenta inválida."}, status=status.HTTP_400_BAD_REQUEST)
        fecha_desde = _parse_fecha(request.query_params.get('desde'))
        fecha_hasta = _parse_fecha(request.query_params.get('hasta'))
        datos = libro_mayor(empresa, cuenta, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)
        if _formato_valido(request) == 'excel':
            return exports.libro_mayor_excel(empresa, cuenta, datos)
        return exports.libro_mayor_pdf(empresa, cuenta, datos, fecha_desde, fecha_hasta, download=True)
