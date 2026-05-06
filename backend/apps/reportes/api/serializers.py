from rest_framework import serializers

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
    estado = serializers.CharField()