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

    def validate(self, attrs):
        variante = attrs.get('variante')
        if variante is not None and variante.producto_id != attrs['producto'].pk:
            raise serializers.ValidationError({'variante': 'La variante no pertenece al producto indicado.'})
        return attrs


def error_motivo_ajuste(motivo, tipo) -> str | None:
    """Un ajuste solo registra movimientos internos -- las compras van por Facturas de Compra."""
    if motivo in AjusteInventario.MOTIVOS_COMPRA:
        return ('Las compras a proveedores se registran en Compras > Facturas de compra '
                '(así quedan en el Libro de Compras y en Cuentas por Pagar).')
    tipos_validos = AjusteInventario.MOTIVOS_INTERNOS.get(motivo)
    if tipos_validos is None:
        return 'Motivo de ajuste inválido.'
    if tipo and tipo not in tipos_validos:
        return f'"{dict(AjusteInventario.MOTIVO_CHOICES)[motivo]}" no aplica a una {tipo}.'
    return None


class AjusteInventarioSerializer(serializers.ModelSerializer):
    """
    Ajuste de entrada/salida de inventario por un motivo INTERNO (conteo
    físico, merma, consumo propio, inventario inicial...). Al crearse,
    aplica de inmediato el movimiento de stock de cada línea (ver
    ``crear_y_aplicar_ajuste``) -- no queda "pendiente". Las compras a
    proveedores ya no pasan por aquí: ver ``FacturaCompra``.
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
            'usuario_nombre', 'fecha_creacion', 'fecha_documento', 'activo',
            'detalles', 'detalles_para_crear',
        )
        # `numero_control` (de la factura de un proveedor) queda solo para
        # leer ajustes históricos; los nuevos no lo usan.
        read_only_fields = ('usuario', 'fecha_creacion', 'numero_control')

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("El ajuste debe incluir al menos una línea de producto.")
        return value

    def validate(self, attrs):
        error = error_motivo_ajuste(attrs.get('motivo', 'otro'), attrs.get('tipo'))
        if error:
            raise serializers.ValidationError({'motivo': error})
        if attrs.get('motivo') != 'devolucion_proveedor':
            attrs['proveedor'] = None

        # Una ENTRADA sin costo deja el costo promedio del producto sin
        # actualizar (ver `stock_service._actualizar_costo_promedio`) y el
        # asiento sin valor. Si la línea no lo trae, se valora al costo
        # promedio que ya tiene el producto (lo correcto para un conteo
        # físico al alza: no cambia el promedio); solo si el producto todavía
        # no tiene costo se le exige al usuario.
        if attrs.get('tipo') == 'entrada':
            for d in attrs.get('detalles', []):
                if d.get('costo_unitario') and d['costo_unitario'] > 0:
                    continue
                item = d.get('variante') or d['producto']
                costo_actual = getattr(item, 'costo_promedio', None)
                if attrs.get('motivo') != 'inventario_inicial' and costo_actual and costo_actual > 0:
                    d['costo_unitario'] = costo_actual
                    continue
                raise serializers.ValidationError({
                    'detalles': f'Indica el costo unitario de "{item}" -- todavía no tiene un costo registrado.',
                })
        return attrs

    def create(self, validated_data):
        detalles_data = validated_data.pop('detalles', [])
        usuario = self.context['request'].user

        try:
            return crear_y_aplicar_ajuste(
                usuario=usuario, detalles_data=detalles_data, **validated_data,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'detalles': str(exc)})


class AjusteInventarioEditSerializer(serializers.ModelSerializer):
    """
    Edición de un ajuste YA aplicado -- deliberadamente NO incluye `tipo`,
    `almacen` ni `detalles`: esos ya movieron stock real, y corregirlos acá
    (en vez de con un ajuste en sentido contrario) desincronizaría el
    kardex. Solo se puede corregir metadata del documento -- típicamente
    la fecha real de la nota/factura del proveedor, cargada después de la
    fecha en que se registró el ajuste en el sistema.
    """
    class Meta:
        model = AjusteInventario
        fields = ('motivo', 'proveedor', 'numero_documento', 'numero_control', 'fecha_documento', 'observaciones')

    def validate_motivo(self, value):
        # Un ajuste histórico de compra conserva su motivo, pero ningún
        # ajuste puede pasar a ser "compra" (ni dejar de serlo) editándolo.
        actual = self.instance.motivo if self.instance else None
        if value == actual:
            return value
        if actual in AjusteInventario.MOTIVOS_COMPRA:
            raise serializers.ValidationError('El motivo de una compra registrada no se puede cambiar.')
        error = error_motivo_ajuste(value, self.instance.tipo if self.instance else None)
        if error:
            raise serializers.ValidationError(error)
        return value
