from rest_framework import serializers
from apps.clientes.models import Cliente

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ('id', 'nombre', 'email', 'telefono', 'direccion', 'tipo_documento', 'documento', 'fecha_registro', 'activo')
        read_only_fields = ('id', 'fecha_registro')