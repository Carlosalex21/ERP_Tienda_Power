from rest_framework import serializers
from apps.configuracion.models import Configuracioniva, Tipodocumentofiscal, ConfiguracionCorrelativo

class ConfiguracionivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuracioniva
        fields = ['id', 'nombre', 'porcentaje_iva', 'activo', 'fecha_creacion']
        read_only_fields = ['fecha_creacion']
    
    def validate_porcentaje_iva(self, value):
        if value < 0:
            raise serializers.ValidationError("El porcentaje de IVA no puede ser negativo.")
        return value
    
    def validate_nombre(self, value):
        if not value or value.strip() == "":
            raise serializers.ValidationError("El nombre de la configuración no puede estar vacío.")
        
        # Validación de unicidad manual para mayor control
        qs = Configuracioniva.objects.filter(nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una configuración de IVA con este nombre.")
        return value

class TipodocumentofiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tipodocumentofiscal
        fields = '__all__'

# Separamos la lectura de la escritura por seguridad (Cumplimiento de Auditoría)
class ConfiguracionCorrelativoReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionCorrelativo
        fields = ['prefijo', 'current_number', 'number_length']

class ConfiguracionCorrelativoWriteSerializer(serializers.ModelSerializer):
    # El campo password es obligatorio para autorizar cambios en la numeración fiscal
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = ConfiguracionCorrelativo
        fields = ['prefijo', 'current_number', 'number_length', 'password']