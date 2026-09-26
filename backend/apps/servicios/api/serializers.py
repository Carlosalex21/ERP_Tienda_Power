from decimal import Decimal

from rest_framework import serializers
from ..models import OrdenServicio


class OrdenServicioSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    tecnico_nombre = serializers.SerializerMethodField()
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True, default=None)

    class Meta:
        model = OrdenServicio
        fields = (
            'id', 'numero', 'cliente', 'cliente_nombre', 'equipo', 'descripcion_falla', 'diagnostico',
            'estado', 'tecnico', 'tecnico_nombre', 'departamento', 'departamento_nombre',
            'costo_estimado', 'factura', 'token_publico',
            'fecha_recepcion', 'fecha_entrega_estimada', 'fecha_entrega_real',
        )
        read_only_fields = ('numero', 'factura', 'token_publico', 'fecha_recepcion', 'fecha_entrega_real')

    def get_tecnico_nombre(self, obj):
        if not obj.tecnico:
            return None
        return obj.tecnico.get_full_name() or obj.tecnico.username


class OrdenServicioPublicoSerializer(serializers.ModelSerializer):
    """
    Lo que ve el cliente al abrir el link/QR de seguimiento de su orden --
    sin datos internos (nada de costos, técnico asignado, diagnóstico
    interno, etc.), solo lo necesario para saber en qué va su equipo.
    """

    class Meta:
        model = OrdenServicio
        fields = ('numero', 'equipo', 'estado', 'fecha_recepcion', 'fecha_entrega_estimada', 'fecha_entrega_real')


class LineaCierreOrdenSerializer(serializers.Serializer):
    """Una línea a facturar al cerrar la orden -- mano de obra o un repuesto real vendido."""
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, default=1)
    monto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class CerrarOrdenServicioSerializer(serializers.Serializer):
    lineas = LineaCierreOrdenSerializer(many=True, allow_empty=False)
    metodo_pago_id = serializers.IntegerField()
    condicion_pago = serializers.ChoiceField(choices=('contado', 'credito'), default='contado')
    moneda_id = serializers.IntegerField(required=False, allow_null=True)
