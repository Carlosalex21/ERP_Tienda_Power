from rest_framework import serializers
from apps.clientes.models import Cliente

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ('id', 'nombre', 'email', 'telefono', 'direccion', 'tipo_documento', 'documento', 'fecha_registro', 'activo')
        read_only_fields = ('id', 'fecha_registro')


class ClienteBulkUploadSerializer(serializers.Serializer):
    """Serializer para validar el archivo subido para la carga masiva de clientes."""
    file = serializers.FileField(help_text="Archivo CSV o Excel (.xlsx) con los clientes a importar.")

    def validate_file(self, value):
        if not value.name.endswith('.csv') and not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("El archivo debe ser de tipo CSV o Excel (.xlsx).")
        return value