from django.db.models import Sum
from rest_framework import serializers
from ..models import LoteProducto


class LoteProductoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_sku = serializers.CharField(source='producto.sku', read_only=True, default=None)
    dias_para_vencer = serializers.IntegerField(read_only=True)
    vencido = serializers.BooleanField(read_only=True)
    # Cuánto stock del producto todavía no está asignado a ningún lote --
    # informativo para el formulario ("te quedan 12 sin lotear").
    stock_sin_lotear = serializers.SerializerMethodField()

    class Meta:
        model = LoteProducto
        fields = (
            'id', 'producto', 'producto_nombre', 'producto_sku', 'numero_lote',
            'fecha_vencimiento', 'cantidad', 'activo', 'dias_para_vencer', 'vencido',
            'stock_sin_lotear',
        )

    def get_stock_sin_lotear(self, obj):
        return self._stock_disponible(obj.producto, excluir_id=obj.pk)

    @staticmethod
    def _stock_disponible(producto, excluir_id=None):
        qs = LoteProducto.objects.filter(producto=producto, activo=True)
        if excluir_id:
            qs = qs.exclude(pk=excluir_id)
        ya_loteado = qs.aggregate(total=Sum('cantidad'))['total'] or 0
        return (producto.cantidad or 0) - ya_loteado

    def validate(self, attrs):
        # La cantidad total loteada de un producto nunca debe superar el
        # stock real que tiene -- sin esto se podía lotear, por ejemplo, el
        # mismo stock varias veces (20 unidades reales -> 60 "loteadas"
        # entre 3 lotes), rompiendo cualquier reporte de vencimientos.
        producto = attrs.get('producto') or getattr(self.instance, 'producto', None)
        cantidad_nueva = attrs.get('cantidad', getattr(self.instance, 'cantidad', 0))
        if producto is not None:
            disponible = self._stock_disponible(producto, excluir_id=self.instance.pk if self.instance else None)
            if cantidad_nueva > disponible:
                raise serializers.ValidationError({
                    'cantidad': (
                        f"Solo quedan {disponible} unidades de \"{producto.nombre}\" sin lotear "
                        f"(stock total: {producto.cantidad})."
                    )
                })
        return attrs
