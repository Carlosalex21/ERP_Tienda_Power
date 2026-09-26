from rest_framework import serializers

from apps.inventario.models import Producto, TrasladoInventario, TrasladoInventarioDetalle
from apps.inventario.services.stock_service import crear_y_aplicar_traslado


class TrasladoInventarioDetalleSerializer(serializers.ModelSerializer):
    """Serializer de lectura de una línea de traslado (con nombre resuelto)."""
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True, default=None)

    class Meta:
        model = TrasladoInventarioDetalle
        fields = (
            'id', 'producto', 'producto_nombre', 'cantidad',
            'stock_resultante_origen', 'stock_resultante_destino',
        )


class TrasladoInventarioDetalleWriteSerializer(serializers.ModelSerializer):
    """Serializer de escritura de una línea de traslado."""
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())

    class Meta:
        model = TrasladoInventarioDetalle
        fields = ('producto', 'cantidad')

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value


class TrasladoInventarioSerializer(serializers.ModelSerializer):
    """
    Traslado de stock entre dos almacenes (cabecera + líneas). Al crearse,
    aplica de inmediato el movimiento -- descuenta del origen y suma al
    destino en la misma operación (ver ``crear_y_aplicar_traslado``); no
    queda "en tránsito" ni pendiente de que alguien confirme la recepción.
    """
    detalles = TrasladoInventarioDetalleSerializer(many=True, read_only=True)
    detalles_para_crear = TrasladoInventarioDetalleWriteSerializer(
        many=True, write_only=True, source='detalles',
    )
    almacen_origen_nombre = serializers.CharField(source='almacen_origen.nombre', read_only=True, default=None)
    almacen_destino_nombre = serializers.CharField(source='almacen_destino.nombre', read_only=True, default=None)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True, default=None)

    class Meta:
        model = TrasladoInventario
        fields = (
            'id', 'almacen_origen', 'almacen_origen_nombre', 'almacen_destino', 'almacen_destino_nombre',
            'observaciones', 'usuario', 'usuario_nombre', 'fecha_creacion',
            'detalles', 'detalles_para_crear',
        )
        read_only_fields = ('usuario', 'fecha_creacion')

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("El traslado debe incluir al menos una línea de producto.")
        return value

    def validate(self, attrs):
        origen = attrs.get('almacen_origen')
        destino = attrs.get('almacen_destino')
        if origen and destino and origen == destino:
            raise serializers.ValidationError({'almacen_destino': 'El almacén de destino debe ser distinto al de origen.'})
        return attrs

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles', [])
        usuario = self.context['request'].user

        try:
            return crear_y_aplicar_traslado(
                usuario=usuario,
                almacen_origen_id=validated_data['almacen_origen'].id,
                almacen_destino_id=validated_data['almacen_destino'].id,
                observaciones=validated_data.get('observaciones', ''),
                detalles_data=[
                    {'producto_id': d['producto'].id, 'cantidad': d['cantidad']} for d in detalles_data
                ],
            )
        except ValueError as exc:
            raise serializers.ValidationError({'detalles': str(exc)})
