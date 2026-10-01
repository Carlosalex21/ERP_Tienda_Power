from rest_framework import serializers
from decimal import Decimal
# IMPORTANTE: Ajusta la ruta de modelos
from apps.inventario.models import (
    Producto, Variacionproducto, Categoriaproducto, Almacen,
    Inventario, Atributo, ValorAtributo, MovimientoInventario,
    Reservastock, Lecturacodigobarras, Productocategoria, PresentacionProducto
)

class AlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Almacen
        fields = '__all__'

    def validate_nombre(self, value):
        if Almacen.objects.filter(nombre=value).exists():
             if not self.instance or self.instance.nombre != value:
                raise serializers.ValidationError("El nombre del almacén ya existe.")
        return value

class CategoriaSerializer(serializers.ModelSerializer):
    padre_nombre = serializers.SerializerMethodField()
    class Meta:
        model = Categoriaproducto
        fields = ['id', 'nombre', 'slug', 'activo', 'padre', 'padre_nombre']

    def get_padre_nombre(self, obj):
        return obj.padre.nombre if obj.padre else "-"

class ValorAtributoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorAtributo
        fields = ['id', 'valor']

class AtributoSerializer(serializers.ModelSerializer):
    valores = ValorAtributoSerializer(many=True, read_only=True)
    class Meta:
        model = Atributo
        fields = ['id', 'nombre', 'valores']

class VariacionproductoSerializer(serializers.ModelSerializer):
    base_imponible = serializers.SerializerMethodField()
    class Meta:
        model = Variacionproducto
        fields = '__all__'

    def get_base_imponible(self, obj):
        if obj.precio and obj.producto.configuracion_iva:
            tasa = obj.producto.configuracion_iva.porcentaje_iva
            return round(obj.precio / (1 + (tasa / 100)), 2)
        return obj.precio

    def update(self, instance, validated_data):
        # `cantidad`/`costo_promedio` solo se escriben aquí AL CREAR la
        # variante (sin stock previo, un set directo ya ES el promedio
        # ponderado correcto). Una vez creada, editarlos por este endpoint
        # dejaría cambiar el stock sin pasar por un Ajuste (sin kardex) y
        # pisaría el costo promedio sin la fórmula ponderada de
        # `stock_service._actualizar_costo_promedio` -- esos cambios deben
        # venir siempre de un Ajuste de Inventario.
        validated_data.pop('cantidad', None)
        validated_data.pop('costo_promedio', None)
        return super().update(instance, validated_data)

class PresentacionProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresentacionProducto
        fields = ['id', 'producto', 'nombre', 'factor_conversion', 'precio', 'es_default', 'activo']


class ProductoSerializer(serializers.ModelSerializer):
    # El modelo Producto no tiene una relación 'variantes'; la relación real es
    # la FK inversa de Variacionproducto (variacionproducto_set). Usamos source
    # para exponerla como 'variantes' sin cambiar el contrato de la API.
    variantes = VariacionproductoSerializer(many=True, read_only=True, source='variacionproducto_set')
    presentaciones = PresentacionProductoSerializer(many=True, read_only=True)
    moneda_codigo = serializers.CharField(source='moneda.codigo', read_only=True, default=None)
    moneda_simbolo = serializers.CharField(source='moneda.simbolo', read_only=True, default=None)
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True, default=None)

    class Meta:
        model = Producto
        fields = '__all__'

    def create(self, validated_data):
        # `moneda` no viene marcado como obligatorio en el formulario (para no
        # romper el flujo de quien no usa multi-moneda), pero si se deja sin
        # asignar por completo el precio queda "flotando" sin saber en qué
        # divisa fue tecleado -- eso es lo que hacía que el POS/catálogo lo
        # reinterpretraran mal al cambiar de moneda. Por defecto se asume la
        # moneda base del tenant, igual que el resto del sistema.
        if validated_data.get('moneda') is None:
            from apps.configuracion.services.conversion_service import (
                get_moneda_base, MonedaNoEncontradaError,
            )
            try:
                validated_data['moneda'] = get_moneda_base()
            except MonedaNoEncontradaError:
                pass
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Mismo motivo que en `VariacionproductoSerializer.update()`: editar
        # un producto YA EXISTENTE no debe poder cambiar su stock (sin
        # kardex) ni su costo promedio (sin la fórmula ponderada) -- eso es
        # lo que hace `apps.inventario.services.stock_service` desde un
        # Ajuste de Inventario (entrada/salida) o la recepción de una orden
        # de compra. `cantidad`/`costo_promedio` solo se aceptan al CREAR
        # (stock inicial del producto, sin stock previo que promediar).
        validated_data.pop('cantidad', None)
        validated_data.pop('costo_promedio', None)
        return super().update(instance, validated_data)

class InventarioSerializer(serializers.ModelSerializer):
    """Desglose de stock por almacén -- ver `apps.inventario.services.stock_service.crear_y_aplicar_traslado`, que es lo único que hoy mantiene `cantidad` al día junto con los Ajustes."""
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True, default=None)
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, default=None)

    class Meta:
        model = Inventario
        fields = '__all__'

class ProductocategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Productocategoria
        fields = '__all__'

class MovimientoInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventario
        fields = '__all__'

class ReservastockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservastock
        fields = '__all__'

class LecturacodigobarrasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lecturacodigobarras
        fields = '__all__'
