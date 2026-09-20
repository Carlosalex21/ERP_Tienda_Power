from decimal import Decimal

from rest_framework import serializers

from ..models import (
    EmpresaContable, CuentaContable, AsientoContable, AsientoContableDetalle,
    AsientoPlantilla, AsientoPlantillaLinea,
)


class EmpresaContableSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)

    class Meta:
        model = EmpresaContable
        fields = (
            'id', 'nombre', 'identificacion_fiscal', 'cliente', 'cliente_nombre', 'activo', 'fecha_creacion',
            'es_negocio_propio', 'cuenta_cobro_default', 'cuenta_ingreso_default', 'cuenta_iva_default',
        )
        read_only_fields = ('fecha_creacion',)

    def validate(self, attrs):
        es_negocio_propio = attrs.get('es_negocio_propio', getattr(self.instance, 'es_negocio_propio', False))
        if es_negocio_propio:
            qs = EmpresaContable.objects.filter(es_negocio_propio=True, activo=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'es_negocio_propio': 'Ya existe otra empresa marcada como el negocio propio -- solo puede haber una.',
                })
        return attrs


class CuentaContableSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaContable
        fields = ('id', 'empresa', 'codigo', 'nombre', 'tipo', 'naturaleza', 'cuenta_padre', 'acepta_movimiento', 'activo')
        read_only_fields = ('naturaleza',)

    def validate(self, attrs):
        from ..services import NATURALEZA_POR_TIPO
        tipo = attrs.get('tipo') or getattr(self.instance, 'tipo', None)
        if tipo:
            attrs['naturaleza'] = NATURALEZA_POR_TIPO[tipo]
        return attrs


class AsientoContableDetalleSerializer(serializers.ModelSerializer):
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True)

    class Meta:
        model = AsientoContableDetalle
        fields = ('id', 'cuenta', 'cuenta_codigo', 'cuenta_nombre', 'debe', 'haber', 'descripcion', 'orden')


class AsientoContableSerializer(serializers.ModelSerializer):
    """Detalle completo de un asiento (lectura) -- incluye sus líneas."""
    detalles = AsientoContableDetalleSerializer(many=True, read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = AsientoContable
        fields = (
            'id', 'empresa', 'numero', 'fecha', 'descripcion', 'estado', 'origen', 'comprobante',
            'usuario', 'usuario_nombre', 'fecha_creacion', 'fecha_anulacion', 'detalles', 'total',
        )
        read_only_fields = ('numero', 'estado', 'origen', 'usuario', 'fecha_creacion', 'fecha_anulacion')

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return None
        return obj.usuario.get_full_name() or obj.usuario.username

    def get_total(self, obj):
        return str(sum((d.debe for d in obj.detalles.all()), Decimal('0.00')))


class LineaAsientoInputSerializer(serializers.Serializer):
    cuenta_id = serializers.IntegerField()
    debe = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0'))
    haber = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0'))
    descripcion = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CrearAsientoContableSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    descripcion = serializers.CharField(max_length=255)
    lineas = LineaAsientoInputSerializer(many=True, allow_empty=False)
    estado = serializers.ChoiceField(choices=('borrador', 'contabilizado'), default='contabilizado')


class LineaHonorarioInputSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, default=1)
    monto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class FacturarHonorariosSerializer(serializers.Serializer):
    lineas = LineaHonorarioInputSerializer(many=True, allow_empty=False)
    metodo_pago_id = serializers.IntegerField()
    cuenta_cobro_id = serializers.IntegerField()
    cuenta_ingreso_id = serializers.IntegerField()
    condicion_pago = serializers.ChoiceField(choices=('contado', 'credito'), default='contado')
    moneda_id = serializers.IntegerField(required=False, allow_null=True)


class AsientoPlantillaLineaSerializer(serializers.ModelSerializer):
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True)

    class Meta:
        model = AsientoPlantillaLinea
        fields = ('id', 'cuenta', 'cuenta_codigo', 'cuenta_nombre', 'debe', 'haber', 'descripcion', 'orden')


class AsientoPlantillaSerializer(serializers.ModelSerializer):
    lineas = AsientoPlantillaLineaSerializer(many=True, read_only=True)

    class Meta:
        model = AsientoPlantilla
        fields = ('id', 'empresa', 'nombre', 'descripcion_asiento', 'activo', 'fecha_creacion', 'lineas')
        read_only_fields = ('fecha_creacion',)


class CrearPlantillaDesdeAsientoSerializer(serializers.Serializer):
    asiento_id = serializers.IntegerField()
    nombre = serializers.CharField(max_length=255)


class CerrarEjercicioSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField()
    fecha_hasta = serializers.DateField()
    cuenta_patrimonio_id = serializers.IntegerField()

    def validate(self, attrs):
        if attrs['fecha_desde'] > attrs['fecha_hasta']:
            raise serializers.ValidationError('La fecha desde no puede ser posterior a la fecha hasta.')
        return attrs


class MarcarConciliadoSerializer(serializers.Serializer):
    detalle_id = serializers.IntegerField()
    conciliado = serializers.BooleanField(default=True)
