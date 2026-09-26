from rest_framework import serializers
from apps.rrhh.models import (
    Horario, DiaFestivo, Asistencia, Sucursal, Departamento, PeriodoNomina, NominaEmpleado,
    ConceptoNomina, NominaEmpleadoConcepto,
)

class SucursalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sucursal
        fields = ('id', 'nombre', 'direccion')


class DepartamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Departamento
        fields = ('id', 'nombre', 'descripcion', 'activo')

class ConceptoNominaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConceptoNomina
        fields = ('id', 'nombre', 'tipo', 'modo', 'valor', 'recurrente', 'activo', 'fecha_creacion')
        read_only_fields = ('fecha_creacion',)


class NominaEmpleadoConceptoSerializer(serializers.ModelSerializer):
    class Meta:
        model = NominaEmpleadoConcepto
        fields = ('id', 'concepto', 'nombre', 'tipo', 'monto')


class NominaEmpleadoSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()
    numero_empleado = serializers.CharField(source='usuario.metadata.numero_empleado', read_only=True, default=None)
    conceptos = NominaEmpleadoConceptoSerializer(many=True, read_only=True)

    class Meta:
        model = NominaEmpleado
        fields = (
            'id', 'usuario', 'usuario_nombre', 'numero_empleado', 'sueldo_base',
            'dias_ausencia', 'deduccion_ausencias', 'horas_extra', 'pago_horas_extra',
            'bonificaciones', 'otras_deducciones', 'total_pagar', 'conceptos',
        )

    def get_usuario_nombre(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username


class PeriodoNominaSerializer(serializers.ModelSerializer):
    empleados = NominaEmpleadoSerializer(many=True, read_only=True)
    total_nomina = serializers.SerializerMethodField()
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PeriodoNomina
        fields = (
            'id', 'fecha_desde', 'fecha_hasta', 'estado', 'fecha_pago',
            'usuario', 'usuario_nombre', 'fecha_creacion', 'empleados', 'total_nomina',
        )
        read_only_fields = ('estado', 'fecha_pago', 'usuario', 'fecha_creacion')

    def get_total_nomina(self, obj):
        return str(sum((e.total_pagar for e in obj.empleados.all()), 0))

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username


class GenerarPeriodoNominaSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField()
    fecha_hasta = serializers.DateField()


class HorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Horario
        fields = '__all__'

class DiaFestivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiaFestivo
        fields = '__all__'

class AsistenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asistencia
        fields = '__all__'

# Nuevos serializers para documentar la respuesta de AttendanceSummaryView
class AttendanceSummaryDetailSerializer(serializers.Serializer):
    total_working_days = serializers.IntegerField(help_text="Total de días laborables en el mes (ejemplo estático).")
    absent_days = serializers.IntegerField(help_text="Días ausente.")
    present_days = serializers.IntegerField(help_text="Días presente.")
    half_days = serializers.IntegerField(help_text="Medios días.")
    late_days = serializers.IntegerField(help_text="Días con llegada tarde.")
    holidays = serializers.IntegerField(help_text="Días festivos en el mes.")

class AttendanceSummaryResponseSerializer(serializers.Serializer):
    current_status = serializers.CharField(help_text="Estado actual del usuario: 'in', 'out', o 'break'.")
    summary = AttendanceSummaryDetailSerializer(help_text="Resumen de asistencia del mes.")
    log = AsistenciaSerializer(many=True, help_text="Registro de asistencias del mes.")