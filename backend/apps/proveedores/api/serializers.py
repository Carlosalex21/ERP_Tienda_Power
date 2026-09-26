from decimal import Decimal

from rest_framework import serializers
from django.core.validators import validate_email
from apps.proveedores.models import Proveedor, CuentaPorPagar, PagoProveedor, OrdenCompra, OrdenCompraDetalle

class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = '__all__'
    
    def validate_email(self, value):
        try:
            validate_email(value)
        except Exception:
            raise serializers.ValidationError("El email no es válido.")
        return value

    def validate_plazo_pago(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El plazo de pago no puede ser negativo.")
        return value


class PagoProveedorSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True, default=None)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PagoProveedor
        fields = ('id', 'cuenta_por_pagar', 'monto', 'metodo_pago', 'metodo_pago_nombre', 'referencia', 'usuario_nombre', 'fecha')
        read_only_fields = ('fecha',)

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username


class CuentaPorPagarSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.nombre', read_only=True)
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    pagos = PagoProveedorSerializer(many=True, read_only=True)

    class Meta:
        model = CuentaPorPagar
        fields = (
            'id', 'proveedor', 'proveedor_nombre', 'numero_documento', 'fecha_emision', 'fecha_vencimiento',
            'monto', 'monto_pagado', 'saldo_pendiente', 'estado', 'ajuste_origen', 'observaciones',
            'fecha_creacion', 'pagos',
        )
        read_only_fields = ('monto_pagado', 'estado', 'ajuste_origen', 'fecha_creacion')


class RegistrarPagoProveedorSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    metodo_pago_id = serializers.IntegerField(required=False, allow_null=True)
    referencia = serializers.CharField(required=False, allow_blank=True, max_length=100)


# --- Órdenes de Compra ---

class OrdenCompraDetalleSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    cantidad_pendiente = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrdenCompraDetalle
        fields = (
            'id', 'producto', 'producto_nombre', 'cantidad_pedida', 'cantidad_recibida',
            'cantidad_pendiente', 'costo_unitario_esperado',
        )
        read_only_fields = ('cantidad_recibida',)


class OrdenCompraDetalleWriteSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)
    costo_unitario_esperado = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)


class OrdenCompraSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.nombre', read_only=True)
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, default=None)
    usuario_nombre = serializers.SerializerMethodField()
    detalles = OrdenCompraDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = OrdenCompra
        fields = (
            'id', 'numero', 'proveedor', 'proveedor_nombre', 'almacen', 'almacen_nombre', 'estado',
            'observaciones', 'usuario', 'usuario_nombre', 'fecha_creacion', 'fecha_envio',
            'fecha_recepcion_completa', 'detalles',
        )
        read_only_fields = ('numero', 'estado', 'usuario', 'fecha_creacion', 'fecha_envio', 'fecha_recepcion_completa')

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username


class CrearOrdenCompraSerializer(serializers.Serializer):
    proveedor_id = serializers.IntegerField()
    almacen_id = serializers.IntegerField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)
    detalles = OrdenCompraDetalleWriteSerializer(many=True, allow_empty=False)


class LineaRecepcionSerializer(serializers.Serializer):
    detalle_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)
    costo_unitario = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, allow_null=True)


class RegistrarRecepcionSerializer(serializers.Serializer):
    numero_documento = serializers.CharField(required=False, allow_blank=True, max_length=100)
    lineas = LineaRecepcionSerializer(many=True, allow_empty=False)