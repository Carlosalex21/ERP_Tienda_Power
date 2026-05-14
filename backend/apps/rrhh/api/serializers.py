from rest_framework import serializers
from apps.rrhh.models import Horario, DiaFestivo, Asistencia, Sucursal

class SucursalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sucursal
        fields = ('id', 'nombre', 'direccion')

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