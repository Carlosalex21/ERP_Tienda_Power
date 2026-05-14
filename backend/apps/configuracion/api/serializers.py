from rest_framework import serializers
from ..models import ConfiguracionEmpresa, Configuracioniva, Tipodocumentofiscal

class ConfiguracionEmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionEmpresa
        fields = ('nombre_comercial', 'razon_social', 'rif', 'telefono', 'direccion', 'logo')

class IvaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuracioniva
        fields = '__all__'

class TipoDocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tipodocumentofiscal
        fields = '__all__'