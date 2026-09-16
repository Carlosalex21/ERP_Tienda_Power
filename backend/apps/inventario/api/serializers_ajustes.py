from rest_framework import serializers

from apps.inventario.models import (
    AjusteInventario, AjusteInventarioDetalle, Producto, Variacionproducto,
)
from apps.inventario.services.stock_service import crear_y_aplicar_ajuste


class AjusteInventarioDetalleSerializer(serializers.ModelSerializer):
    """Serializer de lectura de una línea de ajuste (con nombre resuelto)."""
    nombre = serializers.SerializerMethodField()

    class Meta:
        model = AjusteInventarioDetalle
        fields = (
            'id', 'nombre', 'producto', 'variante', 'cantidad',
            'costo_unitario', 'stock_resultante',
        )

    def get_nombre(self, obj):
        if obj.variante is not None:
            return f"{obj.producto.nombre} ({obj.variante.nombre})" if obj.producto else obj.variante.nombre
        return obj.producto.nombre if obj.producto else None


class AjusteInventarioDetalleWriteSerializer(serializers.ModelSerializer):
    """Serializer de escritura de una línea de ajuste."""
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    variante = serializers.PrimaryKeyRelatedField(
        queryset=Variacionproducto.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = AjusteInventarioDetalle
        fields = ('producto', 'variante', 'cantidad', 'costo_unitario')

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value


class AjusteInventarioSerializer(serializers.ModelSerializer):
    """
    Ajuste de entrada/salida de inventario (cabecera + líneas), para el caso
    de mercancía recibida con nota de entrega (sin factura) o correcciones
    de conteo físico. Al crearse, aplica de inmediato el movimiento de stock
    de cada línea (ver ``crear_y_aplicar_ajuste``) -- no queda "pendiente".
    """
    detalles = AjusteInventarioDetalleSerializer(many=True, read_only=True)
    detalles_para_crear = AjusteInventarioDetalleWriteSerializer(
        many=True, write_only=True, source='detalles'
    )
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True, default=None)
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    motivo_display = serializers.CharField(source='get_motivo_display', read_only=True)

    class Meta:
        model = AjusteInventario
        fields = (
            'id', 'tipo', 'tipo_display', 'motivo', 'motivo_display', 'almacen',
            'proveedor', 'numero_documento', 'numero_control', 'observaciones', 'usuario',
            'usuario_nombre', 'fecha_creacion', 'activo',
            'detalles', 'detalles_para_crear',
        )
        read_only_fields = ('usuario', 'fecha_creacion')

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("El ajuste debe incluir al menos una línea de producto.")
        return value

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles', [])
        usuario = self.context['request'].user

        try:
            return crear_y_aplicar_ajuste(
                usuario=usuario, detalles_data=detalles_data, **validated_data,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'detalles': str(exc)})
