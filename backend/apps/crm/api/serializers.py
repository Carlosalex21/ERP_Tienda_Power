from decimal import Decimal

from rest_framework import serializers

from ..models import Cotizacion, CotizacionDetalle, Oportunidad


class OportunidadSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    nombre_contacto = serializers.CharField(read_only=True)
    usuario_asignado_nombre = serializers.SerializerMethodField()
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True, default=None)

    class Meta:
        model = Oportunidad
        fields = (
            'id', 'titulo', 'cliente', 'cliente_nombre', 'nombre_prospecto', 'telefono_prospecto',
            'nombre_contacto', 'etapa', 'valor_estimado', 'fecha_cierre_estimada', 'proximo_seguimiento',
            'usuario_asignado', 'usuario_asignado_nombre', 'departamento', 'departamento_nombre',
            'observaciones', 'motivo_perdida', 'fecha_creacion', 'fecha_actualizacion',
        )
        read_only_fields = ('fecha_creacion', 'fecha_actualizacion')

    def get_usuario_asignado_nombre(self, obj):
        if not obj.usuario_asignado:
            return None
        return obj.usuario_asignado.get_full_name() or obj.usuario_asignado.username


class CambiarEtapaOportunidadSerializer(serializers.Serializer):
    etapa = serializers.ChoiceField(choices=[c[0] for c in Oportunidad.ETAPA_CHOICES])
    motivo_perdida = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CotizacionDetalleSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    variante_nombre = serializers.CharField(source='variante.nombre', read_only=True, default=None)
    subtotal_linea = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CotizacionDetalle
        fields = ('id', 'producto', 'producto_nombre', 'variante', 'variante_nombre', 'cantidad', 'precio_unitario', 'subtotal_linea')


class CotizacionDetalleWriteSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    variante_id = serializers.IntegerField(required=False, allow_null=True)
    cantidad = serializers.IntegerField(min_value=1)
    precio_unitario = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))


class CotizacionSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    nombre_contacto = serializers.CharField(read_only=True)
    moneda_codigo = serializers.CharField(source='moneda.codigo', read_only=True, default=None)
    usuario_nombre = serializers.SerializerMethodField()
    detalles = CotizacionDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = Cotizacion
        fields = (
            'id', 'numero', 'oportunidad', 'cliente', 'cliente_nombre', 'nombre_prospecto', 'telefono_prospecto',
            'nombre_contacto', 'estado', 'moneda', 'moneda_codigo', 'subtotal', 'iva_total', 'total',
            'fecha_emision', 'fecha_vencimiento', 'observaciones', 'usuario', 'usuario_nombre',
            'factura_generada', 'token_publico', 'fecha_creacion', 'detalles',
        )
        read_only_fields = (
            'numero', 'estado', 'subtotal', 'iva_total', 'total', 'fecha_emision', 'usuario',
            'factura_generada', 'token_publico', 'fecha_creacion',
        )

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username


class CrearCotizacionSerializer(serializers.Serializer):
    cliente_id = serializers.IntegerField(required=False, allow_null=True)
    nombre_prospecto = serializers.CharField(required=False, allow_blank=True, max_length=150)
    telefono_prospecto = serializers.CharField(required=False, allow_blank=True, max_length=30)
    oportunidad_id = serializers.IntegerField(required=False, allow_null=True)
    moneda_id = serializers.IntegerField(required=False, allow_null=True)
    fecha_vencimiento = serializers.DateField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)
    detalles = CotizacionDetalleWriteSerializer(many=True, allow_empty=False)


class CambiarEstadoCotizacionSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=[c[0] for c in Cotizacion.ESTADO_CHOICES])


class ConvertirCotizacionSerializer(serializers.Serializer):
    condicion_pago = serializers.ChoiceField(choices=('contado', 'credito'), default='contado')
    almacen_id = serializers.IntegerField(required=False, allow_null=True)


class CotizacionPublicaSerializer(serializers.ModelSerializer):
    """Lo que ve el cliente en el link público -- sin datos internos (usuario, IDs de sistema)."""
    detalles = CotizacionDetalleSerializer(many=True, read_only=True)

    class Meta:
        model = Cotizacion
        fields = ('numero', 'estado', 'subtotal', 'total', 'fecha_emision', 'fecha_vencimiento', 'detalles')
