from rest_framework import serializers
from decimal import Decimal
# IMPORTANTE: Ajusta la ruta de modelos
from erp.models import Producto, Variacionproducto, Categoriaproducto, Almacen, Inventario, Atributo, ValorAtributo

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

class ProductoSerializer(serializers.ModelSerializer):
    variantes = VariacionproductoSerializer(many=True, read_only=True)
    class Meta:
        model = Producto
        fields = '__all__'