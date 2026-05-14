from rest_framework import serializers

class PublicOrderItemSerializer(serializers.Serializer):
    variacion_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)

class PublicCreateOrderSerializer(serializers.Serializer):
    """
    Serializer para validar los datos de un nuevo pedido creado por un cliente
    desde el catálogo público.
    """
    cliente_nombre = serializers.CharField(max_length=100)
    cliente_telefono = serializers.CharField(max_length=20)
    cliente_direccion = serializers.CharField(max_length=255, required=False)
    items = PublicOrderItemSerializer(many=True, min_length=1)

class PublicProductoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    precio_venta = serializers.DecimalField(max_digits=10, decimal_places=2)
    imagen_url = serializers.SerializerMethodField()

    def get_imagen_url(self, obj):
        request = self.context.get('request')
        if obj.imagen and hasattr(obj.imagen, 'url'):
            return request.build_absolute_uri(obj.imagen.url)
        return None