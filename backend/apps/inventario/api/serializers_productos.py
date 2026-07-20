from rest_framework import serializers

class ProductoBulkUploadSerializer(serializers.Serializer):
    """
    Serializer para validar el archivo subido para la carga masiva de productos.
    """
    file = serializers.FileField(help_text="Archivo CSV o Excel (.xlsx) con los productos a importar.")

    def validate_file(self, value):
        """
        Valida la extensión del archivo.
        """
        if not value.name.endswith('.csv') and not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("El archivo debe ser de tipo CSV o Excel (.xlsx).")
        return value