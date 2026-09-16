from rest_framework import serializers

from apps.reportes.models import Reportecliente, Reporteinventario, Reporteventa
from apps.facturacion.models import Factura

class DashboardResponseSerializer(serializers.Serializer):
    """
    Serializer para validar la estructura de salida del Dashboard.
    Aunque el Dashboard es lectura, esto ayuda a documentar la API.
    """
    userInfo = serializers.DictField()
    resumen = serializers.DictField()
    graficoVentas = serializers.DictField()
    productosMasVendidos = serializers.ListField()
    productosBajoStock = serializers.ListField()
    infoGeneral = serializers.DictField()

class VentaReporteSerializer(serializers.Serializer):
    """Para reportes de listados de ventas."""
    id = serializers.IntegerField()
    correlativo = serializers.CharField()
    fecha_operacion = serializers.DateTimeField()
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    # Moneda en la que se emitió ESTA factura y el mismo total ya convertido
    # a la moneda base del tenant (con la tasa de cambio congelada en la
    # factura, no la de hoy) -- un reporte de ventas mezclando facturas en
    # distintas monedas necesita esto para no sumar dólares con bolívares
    # como si fueran la misma unidad.
    moneda_codigo = serializers.CharField(source='moneda.codigo', read_only=True, default=None)
    total_base = serializers.DecimalField(max_digits=14, decimal_places=2)
    estado = serializers.CharField()

class ReporteclienteSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    producto_mas_comprado_nombre = serializers.CharField(source='producto_mas_comprado.nombre', read_only=True)
    class Meta:
        model = Reportecliente
        fields = '__all__'

class FacturaReportSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)
    moneda_codigo = serializers.CharField(source='moneda.codigo', read_only=True, default=None)
    class Meta:
        model = Factura
        fields = ['id', 'correlativo', 'fecha_operacion', 'cliente_nombre', 'total', 'moneda_codigo', 'total_base', 'estado', 'metodo_pago_nombre']

class FacturaReporteSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    detalles = serializers.SerializerMethodField()
    moneda_codigo = serializers.CharField(source='moneda.codigo', read_only=True, default=None)
    class Meta:
        model = Factura
        fields = ['id', 'correlativo', 'fecha_operacion', 'cliente_nombre', 'total', 'moneda_codigo', 'total_base', 'estado', 'detalles']

    def get_detalles(self, obj):
        return [
            {
                "producto": d.producto.nombre, 
                "cantidad": d.cantidad, 
                "precio_unitario": d.precio_unitario,
                "total_linea": d.total_linea
            } for d in obj.detalles.all()
        ]