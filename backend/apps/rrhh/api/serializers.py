from rest_framework import serializers
from erp.models import Asistencia, Horario, DiaFestivo, Descanso

class DescansoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Descanso
        fields = '__all__'

class AsistenciaSerializer(serializers.ModelSerializer):
    descansos = DescansoSerializer(many=True, read_only=True)
    class Meta:
        model = Asistencia
        fields = '__all__'

class HorarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Horario
        fields = '__all__'

class DiaFestivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiaFestivo
        fields = '__all__'