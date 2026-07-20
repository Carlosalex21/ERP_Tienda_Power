from rest_framework import serializers
from apps.facturacion.models import Factura, Detallefactura, MetodoPago, Transaccionpago, Cupondescuento, Devolucion
from apps.configuracion.models import ConfiguracionCorrelativo
from apps.inventario.models import Producto, Variacionproducto
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura


class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

class DetallefacturaSerializer(serializers.ModelSerializer):
    nombre = serializers.SerializerMethodField()
    class Meta:
        model = Detallefactura
        fields = ['id', 'nombre', 'cantidad', 'precio_unitario', 'total_linea', 'producto', 'variante']

    def get_nombre(self, obj):
        return f"{obj.producto.nombre} ({obj.variante.nombre})" if obj.variante else obj.producto.nombre

class DetallefacturaWriteSerializer(serializers.ModelSerializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    variante = serializers.PrimaryKeyRelatedField(queryset=Variacionproducto.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Detallefactura
        fields = ['producto', 'variante', 'cantidad', 'precio_unitario']

class FacturaSerializer(serializers.ModelSerializer):
    detalles = DetallefacturaSerializer(many=True, read_only=True)
    # Este campo permite recibir los detalles para la creación. El frontend seguirá usando la clave 'detalles'.
    detalles_para_crear = DetallefacturaWriteSerializer(many=True, write_only=True, source='detalles')

    class Meta:
        model = Factura
        fields = [
            'id', 'usuario', 'cliente', 'orden', 'fecha_operacion', 'correlativo',
            'subtotal', 'descuento_global', 'iva_total', 'total', 'almacen',
            'estado', 'metodo_pago', 'nif_factura', 'activo',
            'nombre_cliente_pendiente', 'comentario_pendiente',
            'detalles', 'detalles_para_crear'
        ]
        read_only_fields = ('subtotal', 'iva_total', 'total', 'correlativo')

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles', [])
        factura = Factura.objects.create(**validated_data)
        for detalle_data in detalles_data:
            Detallefactura.objects.create(factura=factura, **detalle_data)
        
        recalcular_y_guardar_factura(factura)
        return factura

class TransaccionpagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaccionpago
        fields = '__all__'

class ConfiguracionCorrelativoReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionCorrelativo
        fields = ['prefijo', 'current_number', 'number_length']

class ConfiguracionCorrelativoWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta:
        model = ConfiguracionCorrelativo
        fields = ['prefijo', 'current_number', 'number_length', 'password']

class CupondescuentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cupondescuento
        fields = '__all__'

class DevolucionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Devolucion
        fields = '__all__'