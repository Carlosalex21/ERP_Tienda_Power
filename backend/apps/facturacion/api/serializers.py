from rest_framework import serializers
from apps.facturacion.models import Factura, Detallefactura, MetodoPago, Transaccionpago, Cupondescuento, Devolucion
from apps.configuracion.models import ConfiguracionCorrelativo

class MetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetodoPago
        fields = '__all__'

class DetallefacturaSerializer(serializers.ModelSerializer):
    nombre = serializers.SerializerMethodField()
    class Meta:
        model = Detallefactura
        fields = ['id', 'nombre', 'cantidad', 'precio_unitario', 'total_linea']

    def get_nombre(self, obj):
        return f"{obj.producto.nombre} ({obj.variante.nombre})" if obj.variante else obj.producto.nombre

class FacturaSerializer(serializers.ModelSerializer):
    detalles = DetallefacturaSerializer(many=True, read_only=True)
    class Meta:
        model = Factura
        fields = '__all__'

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