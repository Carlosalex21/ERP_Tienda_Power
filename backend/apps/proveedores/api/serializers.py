from rest_framework import serializers
from django.core.validators import validate_email
from apps.proveedores.models import Proveedor

class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = '__all__'
    
    def validate_email(self, value):
        try:
            validate_email(value)
        except Exception:
            raise serializers.ValidationError("El email no es válido.")
        return value

    def validate_plazo_pago(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El plazo de pago no puede ser negativo.")
        return value