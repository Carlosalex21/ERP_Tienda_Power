from decimal import Decimal

from rest_framework import serializers

from ..models import Mesa, PedidoMesa, PedidoMesaItem


class MesaSerializer(serializers.ModelSerializer):
    estado = serializers.SerializerMethodField()
    pedido_abierto_id = serializers.SerializerMethodField()

    class Meta:
        model = Mesa
        fields = ('id', 'numero', 'capacidad', 'activo', 'estado', 'pedido_abierto_id')

    def get_estado(self, obj):
        return 'ocupada' if obj.pedido_abierto else 'libre'

    def get_pedido_abierto_id(self, obj):
        pedido = obj.pedido_abierto
        return pedido.id if pedido else None


class PedidoMesaItemSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = PedidoMesaItem
        fields = ('id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'notas', 'subtotal')
        read_only_fields = ('precio_unitario',)


class PedidoMesaSerializer(serializers.ModelSerializer):
    """Detalle de un pedido de mesa para el panel (requiere sesión)."""

    mesa_numero = serializers.CharField(source='mesa.numero', read_only=True)
    mesero_nombre = serializers.SerializerMethodField()
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    items = PedidoMesaItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PedidoMesa
        fields = (
            'id', 'mesa', 'mesa_numero', 'mesero', 'mesero_nombre', 'cliente', 'cliente_nombre',
            'estado', 'factura', 'token_publico', 'division_personas', 'propina_pct',
            'mesero_solicitado', 'cuenta_solicitada', 'fecha_apertura', 'fecha_cierre',
            'items', 'total',
        )
        read_only_fields = ('estado', 'factura', 'token_publico', 'fecha_apertura', 'fecha_cierre')

    def get_mesero_nombre(self, obj):
        if not obj.mesero:
            return None
        return obj.mesero.get_full_name() or obj.mesero.username

    def get_total(self, obj):
        return str(sum((item.subtotal for item in obj.items.all()), start=0))


class AgregarItemSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, default=1)
    notas = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CerrarPedidoSerializer(serializers.Serializer):
    metodo_pago_id = serializers.IntegerField()
    condicion_pago = serializers.ChoiceField(choices=('contado', 'credito'), default='contado')
    moneda_id = serializers.IntegerField(required=False, allow_null=True)


class PedidoMesaPublicoSerializer(serializers.ModelSerializer):
    """
    Lo que ve un comensal al escanear el QR de la mesa -- sin datos internos
    (nada de costos, nombre del mesero, ID de cliente interno, etc.), solo
    lo necesario para revisar el pedido y dividir la cuenta.
    """

    mesa_numero = serializers.CharField(source='mesa.numero', read_only=True)
    items = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = PedidoMesa
        fields = (
            'mesa_numero', 'estado', 'items', 'total',
            'division_personas', 'propina_pct', 'mesero_solicitado', 'cuenta_solicitada',
        )

    def get_items(self, obj):
        return [
            {
                'nombre': item.producto.nombre,
                'cantidad': item.cantidad,
                'precio_unitario': str(item.precio_unitario),
                'subtotal': str(item.subtotal),
            }
            for item in obj.items.select_related('producto').all()
        ]

    def get_total(self, obj):
        return str(sum((item.subtotal for item in obj.items.all()), start=0))


class ActualizarDivisionSerializer(serializers.Serializer):
    """Lo que cualquiera que escaneó el QR puede ajustar -- estado compartido por mesa."""

    division_personas = serializers.IntegerField(min_value=1, required=False)
    propina_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0'), max_value=Decimal('100'), required=False,
    )
