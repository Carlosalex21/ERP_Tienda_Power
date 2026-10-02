from decimal import Decimal

from rest_framework import serializers
from django.core.validators import validate_email
from apps.proveedores.models import (
    Proveedor, CuentaPorPagar, PagoProveedor, OrdenCompra, OrdenCompraDetalle, FacturaCompra, FacturaCompraDetalle,
)

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
    factura_compra_total = serializers.DecimalField(source='factura_compra.total', max_digits=14, decimal_places=2, read_only=True, default=None)
    factura_compra_retenido = serializers.SerializerMethodField()

    class Meta:
        model = CuentaPorPagar
        fields = (
            'id', 'proveedor', 'proveedor_nombre', 'numero_documento', 'fecha_emision', 'fecha_vencimiento',
            'monto', 'monto_pagado', 'saldo_pendiente', 'estado', 'ajuste_origen', 'factura_compra',
            'factura_compra_total', 'factura_compra_retenido', 'observaciones', 'fecha_creacion', 'pagos',
        )
        read_only_fields = ('monto_pagado', 'estado', 'ajuste_origen', 'factura_compra', 'fecha_creacion')

    def get_factura_compra_retenido(self, obj):
        return str(obj.factura_compra.total_retenido) if obj.factura_compra_id else None


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


# --- Facturas de Compra ---

class FacturaCompraDetalleSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    variante_nombre = serializers.CharField(source='variante.nombre', read_only=True, default=None)
    subtotal = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = FacturaCompraDetalle
        fields = (
            'id', 'producto', 'producto_nombre', 'variante', 'variante_nombre', 'orden_detalle',
            'cantidad', 'costo_unitario', 'subtotal',
        )


class FacturaCompraSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.nombre', read_only=True)
    proveedor_rif = serializers.CharField(source='proveedor.identificador_fiscal', read_only=True)
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, default=None)
    orden_compra_numero = serializers.CharField(source='orden_compra.numero', read_only=True, default=None)
    tipo_documento_display = serializers.CharField(source='get_tipo_documento_display', read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    neto_a_pagar = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    saldo_pendiente = serializers.SerializerMethodField()
    detalles = FacturaCompraDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = FacturaCompra
        fields = (
            'id', 'proveedor', 'proveedor_nombre', 'proveedor_rif', 'tipo_documento', 'tipo_documento_display',
            'numero_factura', 'numero_control', 'fecha_emision', 'orden_compra', 'orden_compra_numero',
            'almacen', 'almacen_nombre', 'monto_exento', 'base_imponible', 'porcentaje_iva', 'iva', 'total',
            'retencion_iva', 'retencion_islr', 'neto_a_pagar', 'saldo_pendiente', 'estado', 'observaciones',
            'usuario_nombre', 'fecha_creacion', 'fecha_anulacion', 'detalles',
        )
        read_only_fields = fields

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username

    def get_saldo_pendiente(self, obj):
        cuenta = next((c for c in obj.cuentas_por_pagar.all() if c.estado != 'anulada'), None)
        return str(cuenta.saldo_pendiente) if cuenta else '0.00'


class FacturaCompraLineaWriteSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    variante_id = serializers.IntegerField(required=False, allow_null=True)
    orden_detalle_id = serializers.IntegerField(required=False, allow_null=True)
    cantidad = serializers.IntegerField(min_value=1)
    costo_unitario = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=Decimal('0.000001'))


class CrearFacturaCompraSerializer(serializers.Serializer):
    proveedor_id = serializers.IntegerField()
    tipo_documento = serializers.ChoiceField(choices=FacturaCompra.TIPO_DOCUMENTO_CHOICES, default='factura')
    numero_factura = serializers.CharField(max_length=50)
    numero_control = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    fecha_emision = serializers.DateField()
    almacen_id = serializers.IntegerField(required=False, allow_null=True)
    orden_compra_id = serializers.IntegerField(required=False, allow_null=True)
    monto_exento = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0'))
    base_imponible = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0'))
    porcentaje_iva = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal('0'))
    porcentaje_retencion_iva = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal('0'))
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')
    detalles = FacturaCompraLineaWriteSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        from apps.inventario.models import Almacen, Producto, Variacionproducto

        proveedor = Proveedor.objects.filter(pk=attrs['proveedor_id'], activo=True).first()
        if proveedor is None:
            raise serializers.ValidationError({'proveedor_id': 'Proveedor no encontrado.'})
        attrs['proveedor'] = proveedor

        attrs['almacen'] = None
        if attrs.get('almacen_id'):
            attrs['almacen'] = Almacen.objects.filter(pk=attrs['almacen_id'], activo=True).first()
            if attrs['almacen'] is None:
                raise serializers.ValidationError({'almacen_id': 'Almacén no encontrado.'})

        attrs['orden_compra'] = None
        if attrs.get('orden_compra_id'):
            attrs['orden_compra'] = OrdenCompra.objects.filter(pk=attrs['orden_compra_id']).first()
            if attrs['orden_compra'] is None:
                raise serializers.ValidationError({'orden_compra_id': 'Orden de compra no encontrada.'})

        productos = Producto.objects.in_bulk([d['producto_id'] for d in attrs['detalles']])
        variantes = Variacionproducto.objects.in_bulk([d['variante_id'] for d in attrs['detalles'] if d.get('variante_id')])
        for d in attrs['detalles']:
            producto = productos.get(d['producto_id'])
            if producto is None:
                raise serializers.ValidationError({'detalles': f'Producto {d["producto_id"]} no encontrado.'})
            variante = variantes.get(d['variante_id']) if d.get('variante_id') else None
            if d.get('variante_id') and (variante is None or variante.producto_id != producto.pk):
                raise serializers.ValidationError({'detalles': f'La variante indicada no pertenece a "{producto.nombre}".'})
            d['producto'] = producto
            d['variante'] = variante
        return attrs