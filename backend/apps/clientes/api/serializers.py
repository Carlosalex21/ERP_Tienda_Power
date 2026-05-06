from rest_framework import serializers
from models import Cliente

class ClienteSerializer(serializers.ModelSerializer):
    """
    Serializer para el modelo Cliente.
    Gestiona la validación de documentos y nombres únicos.
    """
    class Meta:
        model = Cliente
        fields = [
            'id', 'tipo_documento', 'documento', 'nombre', 'email', 
            'telefono', 'direccion', 'codigo_postal', 'provincia', 'fecha_registro'
        ]
        
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
            'direccion': {'required': False, 'allow_blank': True},
            'codigo_postal': {'required': False, 'allow_blank': True},
            'provincia': {'required': False, 'allow_blank': True},
            'fecha_registro': {'read_only': True} 
        }

    def validate_documento(self, value):
        qs = Cliente.objects.filter(documento__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un cliente con este número de documento.")
        return value

    def validate_nombre(self, value):
        qs = Cliente.objects.filter(nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un cliente con este nombre.")
        return value