from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import date, datetime, timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from apps.core.permissions import IsTenantAdmin

from apps.rrhh.models import Horario, DiaFestivo, Asistencia, Descanso, Sucursal, Departamento, PeriodoNomina, ConceptoNomina, NominaEmpleado, ConfiguracionRRHH, VacacionTomada
from apps.rrhh.api.serializers import (
    HorarioSerializer, DiaFestivoSerializer, AsistenciaSerializer, SucursalSerializer,
    AttendanceSummaryResponseSerializer, DepartamentoSerializer,
    PeriodoNominaSerializer, GenerarPeriodoNominaSerializer, ConceptoNominaSerializer,
    NominaEmpleadoSerializer, AgregarConceptoManualSerializer,
    ConfiguracionRRHHSerializer, VacacionTomadaSerializer, RegistrarVacacionSerializer,
    VacacionesResumenSerializer, LiquidacionSerializer,
)
from apps.rrhh.services import (
    generar_periodo_nomina, pagar_periodo_nomina, agregar_concepto_manual, quitar_concepto_manual,
    calcular_vacaciones, registrar_vacacion_tomada, eliminar_vacacion_tomada, calcular_liquidacion, NominaError,
)

def get_working_days(year, month):
    """Calcula los días laborables (L-V) de un mes."""
    from calendar import monthrange
    _, num_days = monthrange(year, month)
    working_days = 0
    for day in range(1, num_days + 1):
        if date(year, month, day).weekday() < 5: # Lunes=0, Viernes=4
            working_days += 1
    return working_days

class SucursalViewSet(viewsets.ModelViewSet):
    """Administra las sucursales del tenant."""
    queryset = Sucursal.objects.all().order_by('nombre', 'id')
    serializer_class = SucursalSerializer
    permission_classes = [IsTenantAdmin]


class DepartamentoViewSet(viewsets.ModelViewSet):
    """Administra los departamentos/equipos de trabajo del tenant (Cocina, Almacén, Taller...)."""
    queryset = Departamento.objects.filter(activo=True)
    serializer_class = DepartamentoSerializer
    permission_classes = [IsTenantAdmin]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])


class ConceptoNominaViewSet(viewsets.ModelViewSet):
    """
    Bonos/deducciones configurables por el tenant (ver `ConceptoNomina`) --
    los `recurrente=True` y `activo=True` se aplican solos en cada nómina
    nueva. No se borran físicamente (ya podrían estar snapshoteados en
    nóminas pasadas vía `NominaEmpleadoConcepto`, protegido con `PROTECT`),
    solo se desactivan.
    """
    queryset = ConceptoNomina.objects.all()
    serializer_class = ConceptoNominaSerializer
    permission_classes = [IsTenantAdmin]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])


class PeriodoNominaViewSet(viewsets.ModelViewSet):
    """
    Períodos de nómina -- solo lectura + creación (que en realidad ejecuta
    `generar_periodo_nomina`, no un `.create()` genérico) y la acción
    `pagar`. No se edita un período ya generado línea por línea: si algo
    está mal, se puede volver a generar con otro rango o pagar y corregir
    a mano en Contabilidad.
    """
    queryset = PeriodoNomina.objects.prefetch_related('empleados__usuario', 'empleados__conceptos')
    serializer_class = PeriodoNominaSerializer
    permission_classes = [IsTenantAdmin]
    http_method_names = ['get', 'post', 'head', 'options']

    def create(self, request, *args, **kwargs):
        serializer = GenerarPeriodoNominaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            periodo = generar_periodo_nomina(
                fecha_desde=serializer.validated_data['fecha_desde'],
                fecha_hasta=serializer.validated_data['fecha_hasta'],
                usuario=request.user,
            )
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(periodo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        periodo = self.get_object()
        try:
            pagar_periodo_nomina(periodo, request.user)
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(periodo).data)


class NominaEmpleadoViewSet(viewsets.GenericViewSet):
    """
    Acciones puntuales sobre UNA línea de nómina ya generada -- agregar o
    quitar un concepto manual (ej. una comisión de ventas, que varía por
    empleado y no encaja como un `ConceptoNomina` recurrente/global). Ver
    `apps.rrhh.services.agregar_concepto_manual`/`quitar_concepto_manual`.
    """
    queryset = NominaEmpleado.objects.select_related('periodo').prefetch_related('conceptos')
    serializer_class = NominaEmpleadoSerializer
    permission_classes = [IsTenantAdmin]

    @action(detail=True, methods=['post'], url_path='conceptos')
    def agregar_concepto(self, request, pk=None):
        nomina_empleado = self.get_object()
        serializer = AgregarConceptoManualSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            agregar_concepto_manual(nomina_empleado, **serializer.validated_data)
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        nomina_empleado.refresh_from_db()
        return Response(self.get_serializer(nomina_empleado).data)

    @action(detail=True, methods=['delete'], url_path=r'conceptos/(?P<concepto_id>\d+)')
    def quitar_concepto(self, request, pk=None, concepto_id=None):
        nomina_empleado = self.get_object()
        concepto_aplicado = nomina_empleado.conceptos.filter(pk=concepto_id).first()
        if concepto_aplicado is None:
            return Response({"error": "Concepto no encontrado en esta línea."}, status=status.HTTP_404_NOT_FOUND)
        try:
            quitar_concepto_manual(concepto_aplicado)
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        nomina_empleado.refresh_from_db()
        return Response(self.get_serializer(nomina_empleado).data)


class ConfiguracionRRHHView(APIView):
    """Parámetros de vacaciones/prestaciones del tenant (ver `ConfiguracionRRHH`) -- mismo patrón que `HorarioDetailView`."""
    permission_classes = [IsTenantAdmin]
    serializer_class = ConfiguracionRRHHSerializer

    def get(self, request):
        config, _ = ConfiguracionRRHH.objects.get_or_create(pk=1)
        return Response(self.serializer_class(config).data)

    def put(self, request):
        config, _ = ConfiguracionRRHH.objects.update_or_create(pk=1, defaults=request.data)
        return Response(self.serializer_class(config).data)


class VacacionesEmpleadoView(APIView):
    """
    Resumen de vacaciones (acumuladas/tomadas/disponibles) de UN empleado y
    registro de nuevos períodos tomados -- ver
    `apps.rrhh.services.calcular_vacaciones`/`registrar_vacacion_tomada`.
    """
    permission_classes = [IsTenantAdmin]

    def get(self, request, usuario_id):
        empleado = get_object_or_404(User, pk=usuario_id)
        resumen = calcular_vacaciones(empleado)
        tomadas = VacacionTomada.objects.filter(usuario=empleado).order_by('-fecha_inicio')
        data = {**resumen, 'tomadas': tomadas}
        return Response(VacacionesResumenSerializer(data).data)

    def post(self, request, usuario_id):
        empleado = get_object_or_404(User, pk=usuario_id)
        serializer = RegistrarVacacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            registrar_vacacion_tomada(empleado, registrado_por=request.user, **serializer.validated_data)
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        resumen = calcular_vacaciones(empleado)
        tomadas = VacacionTomada.objects.filter(usuario=empleado).order_by('-fecha_inicio')
        return Response(VacacionesResumenSerializer({**resumen, 'tomadas': tomadas}).data, status=status.HTTP_201_CREATED)


class VacacionTomadaDetailView(APIView):
    """Elimina un período de vacaciones registrado por error."""
    permission_classes = [IsTenantAdmin]

    def delete(self, request, vacacion_id):
        vacacion = get_object_or_404(VacacionTomada, pk=vacacion_id)
        eliminar_vacacion_tomada(vacacion)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LiquidacionCalculadoraView(APIView):
    """
    Calculadora de referencia de la liquidación de un empleado (vacaciones
    pendientes + prestaciones acumuladas según `ConfiguracionRRHH`) -- no
    paga ni registra nada, ver `apps.rrhh.services.calcular_liquidacion`.
    """
    permission_classes = [IsTenantAdmin]

    @extend_schema(
        summary="Calcular la liquidación de referencia de un empleado a una fecha de egreso",
        parameters=[OpenApiParameter(name='fecha_egreso', type=OpenApiTypes.DATE, required=True, location=OpenApiParameter.QUERY)],
        responses=LiquidacionSerializer,
    )
    def get(self, request, usuario_id):
        empleado = get_object_or_404(User, pk=usuario_id)
        fecha_egreso_str = request.query_params.get('fecha_egreso')
        if not fecha_egreso_str:
            return Response({"error": "Falta el parámetro 'fecha_egreso'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            fecha_egreso = date.fromisoformat(fecha_egreso_str)
        except ValueError:
            return Response({"error": "Formato de fecha inválido (usa AAAA-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            resultado = calcular_liquidacion(empleado, fecha_egreso)
        except NominaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LiquidacionSerializer(resultado).data)


class HorarioDetailView(APIView):
    permission_classes = [IsTenantAdmin]
    serializer_class = HorarioSerializer

    @extend_schema(
        summary="Obtener el horario de la empresa",
        responses=HorarioSerializer
    )
    def get(self, request, pk=None):
        # Se asume un único horario por empresa, con pk=1
        horario, _ = Horario.objects.get_or_create(pk=1)
        serializer = self.serializer_class(horario)
        return Response(serializer.data)

    @extend_schema(
        summary="Actualizar el horario de la empresa",
        request=HorarioSerializer,
        responses=HorarioSerializer
    )
    def put(self, request, pk=None):
        # Se asume un único horario por empresa, con pk=1
        horario, created = Horario.objects.update_or_create(
            pk=1,
            defaults=request.data
        )
        serializer = self.serializer_class(horario)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

class DiaFestivoListView(generics.ListCreateAPIView):
    permission_classes = [IsTenantAdmin]
    queryset = DiaFestivo.objects.all().order_by('fecha')
    serializer_class = DiaFestivoSerializer

class DiaFestivoDetailView(generics.DestroyAPIView):
    permission_classes = [IsTenantAdmin]
    queryset = DiaFestivo.objects.all()
    serializer_class = DiaFestivoSerializer

class AttendanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Obtiene el resumen de asistencia del mes para el usuario autenticado",
        responses=AttendanceSummaryResponseSerializer
    )
    def get(self, request):
        today = timezone.localdate()
        start_of_month = today.replace(day=1)
        
        asistencia_hoy = Asistencia.objects.filter(usuario=request.user, fecha=today).first()
        current_status = asistencia_hoy.estado_actual if asistencia_hoy else 'out'

        asistencias_mes = Asistencia.objects.filter(usuario=request.user, fecha__range=[start_of_month, today]).prefetch_related('descansos')
        festivos_mes = DiaFestivo.objects.filter(fecha__range=[start_of_month, today]).count()

        total_working_days = get_working_days(today.year, today.month) - festivos_mes

        summary = {
            "total_working_days": total_working_days,
            "absent_days": asistencias_mes.filter(estado='Ausente').count(),
            "present_days": asistencias_mes.filter(estado='Presente').count(),
            "half_days": asistencias_mes.filter(estado='Medio Día').count(),
            "late_days": asistencias_mes.filter(llegada_tarde=True).count(),
            "holidays": festivos_mes,
        }

        log_serializer = AsistenciaSerializer(asistencias_mes, many=True)
        response_data = {"current_status": current_status, "summary": summary, "log": log_serializer.data}
        return Response(response_data)

class ClockInView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Registra la entrada del usuario (Clock In)",
        request=None,
        responses={200: None}
    )
    def post(self, request):
        now = timezone.now()
        local_date = timezone.localdate()
        horario = Horario.objects.first()
        es_tarde = False
        if horario:
            hora_entrada_limite = datetime.combine(now.date(), horario.hora_entrada_oficial)
            hora_entrada_limite = timezone.make_aware(hora_entrada_limite)
            limite_con_margen = hora_entrada_limite + timedelta(minutes=horario.margen_tardanza_minutos)
            if now > limite_con_margen:
                es_tarde = True

        asistencia, created = Asistencia.objects.get_or_create(
            usuario=request.user,
            fecha=local_date,
            defaults={'hora_entrada': now, 'estado_actual': 'in', 'llegada_tarde': es_tarde}
        )
        if not created:
            asistencia.hora_entrada = now
            asistencia.estado_actual = 'in'
            asistencia.llegada_tarde = es_tarde
            asistencia.save()
        return Response(status=status.HTTP_200_OK)

class ClockOutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Registra la salida del usuario (Clock Out)",
        request=None,
        responses={200: None}
    )
    def post(self, request):
        Asistencia.objects.filter(usuario=request.user, fecha=timezone.localdate()).update(
            hora_salida=timezone.now(),
            estado_actual='out'
        )
        return Response(status=status.HTTP_200_OK)

class BreakView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Inicia o finaliza un descanso para el usuario",
        request={'application/json': {'example': {'start': True}}}
    )
    def post(self, request):
        start_break = request.data.get('start', True)
        asistencia = Asistencia.objects.get(usuario=request.user, fecha=timezone.localdate())
        
        if start_break:
            Descanso.objects.create(asistencia=asistencia, inicio_descanso=timezone.now())
            asistencia.estado_actual = 'break'
        else:
            ultimo_descanso = asistencia.descansos.filter(fin_descanso__isnull=True).last()
            if ultimo_descanso:
                ultimo_descanso.fin_descanso = timezone.now()
                ultimo_descanso.save()
            asistencia.estado_actual = 'in'
        asistencia.save()
        return Response(status=status.HTTP_200_OK)
