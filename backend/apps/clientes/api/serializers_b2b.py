from rest_framework import serializers
from ..models import ClienteB2B, NivelPrecio

class ClienteB2BBulkUploadSerializer(serializers.Serializer):
    """
    Serializer para validar el archivo subido para la carga masiva de clientes B2B.
    """
    file = serializers.FileField(help_text="Archivo CSV o Excel (.xlsx) con los clientes a importar.")

    def validate_file(self, value):
        """
        Valida la extensión del archivo.
        """
        if not value.name.endswith('.csv') and not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("El archivo debe ser de tipo CSV o Excel (.xlsx).")
        return value

class B2BAccountActivationSerializer(serializers.Serializer):
    """
    Serializer para activar una cuenta B2B y establecer la contraseña.
    """
    token = serializers.UUIDField(required=True, help_text="Token de invitación recibido por correo.")
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="La nueva contraseña para la cuenta.")
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="Confirmación de la contraseña.")

    def validate(self, data):
        """
        Verifica que las contraseñas coincidan.
        """
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        # Aquí se podrían añadir validadores de fortaleza de contraseña si se desea.
        return data

class NivelPrecioB2BSerializer(serializers.ModelSerializer):
    """
    Serializer para mostrar la información del Nivel de Precio de un cliente B2B.
    """
    class Meta:
        model = NivelPrecio
        fields = ('nombre', 'porcentaje_descuento')

class ClienteB2BProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para exponer el perfil de un cliente B2B autenticado.
    """
    nivel_precio = NivelPrecioB2BSerializer(read_only=True)

    class Meta:
        model = ClienteB2B
        fields = (
            'razon_social',
            'rif',
            'email_contacto',
            'telefono_contacto',
            'nivel_precio',
            'limite_credito',
            'estado',
        )