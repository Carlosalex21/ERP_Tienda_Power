from decimal import Decimal

from rest_framework import serializers

from apps.core.uploads import validar_archivo_subido
from apps.inmuebles.models import (
    Cargo, ConsultaPropiedad, Contrato, Edificio, GastoComun, GastoPropiedad, Liquidacion, LiquidacionLinea, MedioPago,
    PagoReportado, PeriodoCondominio, Recibo, ReciboAplicacion, Unidad, UnidadFoto, validar_periodo,
)


def _url(archivo, request):
    if archivo and hasattr(archivo, 'url'):
        return request.build_absolute_uri(archivo.url) if request else archivo.url
    return None


class EdificioSerializer(serializers.ModelSerializer):
    unidades_count = serializers.SerializerMethodField()

    class Meta:
        model = Edificio
        fields = '__all__'

    def get_unidades_count(self, obj):
        return getattr(obj, 'unidades_activas', None) if hasattr(obj, 'unidades_activas') else obj.unidades.filter(activo=True).count()


class UnidadFotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = UnidadFoto
        fields = ('id', 'url', 'orden', 'es_portada')

    def get_url(self, obj):
        return _url(obj.imagen, self.context.get('request'))


class UnidadSerializer(serializers.ModelSerializer):
    edificio_nombre = serializers.CharField(source='edificio.nombre', read_only=True, default=None)
    propietario_nombre = serializers.CharField(source='propietario.nombre', read_only=True, default=None)
    ocupante_nombre = serializers.CharField(source='ocupante.nombre', read_only=True, default=None)
    portada_url = serializers.SerializerMethodField()
    fotos = UnidadFotoSerializer(many=True, read_only=True)
    saldo_pendiente_usd = serializers.SerializerMethodField()
    vencido_usd = serializers.SerializerMethodField()
    amenidades = serializers.ListField(child=serializers.CharField(max_length=40), required=False)

    class Meta:
        model = Unidad
        fields = '__all__'
        # La unicidad (edificio + código) se valida a mano en `validate`: el validador automático de DRF
        # volvería obligatorio el edificio y una propiedad suelta de inmobiliaria no tiene.
        validators = []
        extra_kwargs = {'edificio': {'required': False, 'allow_null': True}}

    def _pendientes(self, obj):
        # `cargos_pendientes` lo precarga el viewset (evita una consulta por unidad).
        if hasattr(obj, 'cargos_pendientes'):
            return obj.cargos_pendientes
        return list(obj.cargos.filter(estado='pendiente'))

    def get_saldo_pendiente_usd(self, obj):
        return str(sum((c.saldo_usd for c in self._pendientes(obj)), Decimal('0.00')))

    def get_vencido_usd(self, obj):
        from django.utils import timezone
        hoy = timezone.localdate()
        return str(sum((c.saldo_usd for c in self._pendientes(obj) if c.fecha_vencimiento < hoy), Decimal('0.00')))

    def get_portada_url(self, obj):
        fotos = list(obj.fotos.all())
        return _url(fotos[0].imagen, self.context.get('request')) if fotos else None

    def validate(self, attrs):
        edificio = attrs.get('edificio', getattr(self.instance, 'edificio', None))
        codigo = (attrs.get('codigo') or getattr(self.instance, 'codigo', '')).strip()
        attrs['codigo'] = codigo
        duplicadas = Unidad.objects.filter(edificio=edificio, codigo__iexact=codigo)
        if self.instance:
            duplicadas = duplicadas.exclude(pk=self.instance.pk)
        if duplicadas.exists():
            raise serializers.ValidationError({'codigo': f'Ya existe una unidad con el código "{codigo}"' + (' en este edificio.' if edificio else '.')})
        if attrs.get('publicada', getattr(self.instance, 'publicada', False)):
            operacion = attrs.get('operacion', getattr(self.instance, 'operacion', 'ninguna'))
            if operacion == 'ninguna':
                raise serializers.ValidationError({'operacion': 'Para publicar la propiedad indica si es en alquiler o en venta.'})
            if operacion in ('alquiler', 'alquiler_venta') and not (attrs.get('canon_usd', getattr(self.instance, 'canon_usd', None))):
                raise serializers.ValidationError({'canon_usd': 'Indica el canon de alquiler para publicarla.'})
            if operacion in ('venta', 'alquiler_venta') and not (attrs.get('precio_venta_usd', getattr(self.instance, 'precio_venta_usd', None))):
                raise serializers.ValidationError({'precio_venta_usd': 'Indica el precio de venta para publicarla.'})
        return attrs


class MedioPagoSerializer(serializers.ModelSerializer):
    edificio_nombre = serializers.CharField(source='edificio.nombre', read_only=True, default=None)

    class Meta:
        model = MedioPago
        fields = '__all__'


class GastoComunSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source='proveedor.nombre', read_only=True, default=None)
    categoria_display = serializers.CharField(source='get_categoria_display', read_only=True)
    comprobante_url = serializers.SerializerMethodField()

    class Meta:
        model = GastoComun
        fields = '__all__'
        read_only_fields = ('usuario',)

    def get_comprobante_url(self, obj):
        return _url(obj.comprobante, self.context.get('request'))

    def validate_comprobante(self, archivo):
        return validar_archivo_subido(archivo, permitir_pdf=True, max_mb=10, campo='comprobante') if archivo else archivo


class PeriodoCondominioSerializer(serializers.ModelSerializer):
    edificio_nombre = serializers.CharField(source='edificio.nombre', read_only=True)
    cuotas = serializers.SerializerMethodField()
    cobrado_usd = serializers.SerializerMethodField()

    class Meta:
        model = PeriodoCondominio
        fields = '__all__'

    def get_cuotas(self, obj):
        return obj.cargos.exclude(estado='anulado').count()

    def get_cobrado_usd(self, obj):
        return str(sum((c.monto_pagado_usd for c in obj.cargos.exclude(estado='anulado')), Decimal('0.00')))


class CargoSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)
    edificio_nombre = serializers.CharField(source='unidad.edificio.nombre', read_only=True, default=None)
    pagador_nombre = serializers.CharField(source='pagador.nombre', read_only=True, default=None)
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    saldo_usd = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    vencido = serializers.SerializerMethodField()

    class Meta:
        model = Cargo
        fields = '__all__'

    def get_vencido(self, obj):
        from django.utils import timezone
        return obj.estado == 'pendiente' and obj.fecha_vencimiento < timezone.localdate() and obj.saldo_usd > 0


class CrearCargoSerializer(serializers.Serializer):
    unidad = serializers.PrimaryKeyRelatedField(queryset=Unidad.objects.filter(activo=True))
    tipo = serializers.ChoiceField(choices=[('extraordinaria', 'Cuota extraordinaria'), ('multa', 'Multa'), ('otro', 'Otro')])
    concepto = serializers.CharField(max_length=200)
    periodo = serializers.CharField(max_length=7, validators=[validar_periodo])
    monto_usd = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    fecha_vencimiento = serializers.DateField()


class ReciboAplicacionSerializer(serializers.ModelSerializer):
    concepto = serializers.CharField(source='cargo.concepto', read_only=True)
    periodo = serializers.CharField(source='cargo.periodo', read_only=True)

    class Meta:
        model = ReciboAplicacion
        fields = ('id', 'cargo', 'concepto', 'periodo', 'monto_usd')


class ReciboSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)
    edificio_nombre = serializers.CharField(source='unidad.edificio.nombre', read_only=True, default=None)
    pagador_nombre = serializers.CharField(source='pagador.nombre', read_only=True, default=None)
    metodo_display = serializers.CharField(source='get_metodo_display', read_only=True)
    aplicaciones = ReciboAplicacionSerializer(many=True, read_only=True)
    comprobante_url = serializers.SerializerMethodField()

    class Meta:
        model = Recibo
        fields = '__all__'

    def get_comprobante_url(self, obj):
        return _url(obj.comprobante, self.context.get('request'))


class RegistrarReciboSerializer(serializers.Serializer):
    unidad = serializers.PrimaryKeyRelatedField(queryset=Unidad.objects.filter(activo=True))
    fecha = serializers.DateField()
    monto_pago = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'))
    moneda_pago = serializers.CharField(max_length=3, default='USD')
    tasa = serializers.DecimalField(max_digits=16, decimal_places=6, required=False, allow_null=True, min_value=Decimal('0.000001'))
    metodo = serializers.ChoiceField(choices=Recibo.METODO_CHOICES, default='transferencia')
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    banco = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    cargos = serializers.PrimaryKeyRelatedField(queryset=Cargo.objects.all(), many=True, required=False)
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')
    comprobante = serializers.FileField(required=False, allow_null=True)

    def validate_comprobante(self, archivo):
        return validar_archivo_subido(archivo, permitir_pdf=True, max_mb=10, campo='comprobante') if archivo else None


class PagoReportadoSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)
    edificio_nombre = serializers.CharField(source='unidad.edificio.nombre', read_only=True, default=None)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    comprobante_url = serializers.SerializerMethodField()
    recibo_numero = serializers.CharField(source='recibo.numero', read_only=True, default=None)
    cargos_detalle = serializers.SerializerMethodField()
    metodo_display = serializers.CharField(source='get_metodo_display', read_only=True)

    class Meta:
        model = PagoReportado
        fields = '__all__'

    def get_comprobante_url(self, obj):
        return _url(obj.comprobante, self.context.get('request'))

    def get_cargos_detalle(self, obj):
        return [{'id': c.pk, 'concepto': c.concepto, 'saldo_usd': str(c.saldo_usd)} for c in obj.cargos.all()]


class AprobarPagoSerializer(serializers.Serializer):
    tasa = serializers.DecimalField(max_digits=16, decimal_places=6, required=False, allow_null=True, min_value=Decimal('0.000001'))
    monto_pago = serializers.DecimalField(max_digits=16, decimal_places=2, required=False, allow_null=True, min_value=Decimal('0.01'))
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')


class RechazarPagoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255)


class ContratoSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)
    edificio_nombre = serializers.CharField(source='unidad.edificio.nombre', read_only=True, default=None)
    inquilino_nombre = serializers.CharField(source='inquilino.nombre', read_only=True)
    propietario_nombre = serializers.CharField(source='propietario.nombre', read_only=True, default=None)
    documento_url = serializers.SerializerMethodField()
    dias_para_vencer = serializers.SerializerMethodField()

    class Meta:
        model = Contrato
        fields = '__all__'
        read_only_fields = ('estado', 'propietario', 'contrato_anterior', 'fecha_rescision', 'motivo_rescision', 'usuario')

    def get_documento_url(self, obj):
        return _url(obj.documento, self.context.get('request'))

    def get_dias_para_vencer(self, obj):
        from django.utils import timezone
        return (obj.fecha_fin - timezone.localdate()).days if obj.estado == 'vigente' else None

    def validate_documento(self, archivo):
        return validar_archivo_subido(archivo, permitir_pdf=True, max_mb=10, campo='documento') if archivo else archivo


class RescindirContratoSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False)
    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class RenovarContratoSerializer(serializers.Serializer):
    nueva_fecha_fin = serializers.DateField()
    nuevo_canon = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, min_value=Decimal('0.01'))


class GastoPropiedadSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)
    propietario_nombre = serializers.CharField(source='unidad.propietario.nombre', read_only=True, default=None)
    comprobante_url = serializers.SerializerMethodField()

    class Meta:
        model = GastoPropiedad
        fields = '__all__'
        read_only_fields = ('liquidacion', 'usuario')

    def get_comprobante_url(self, obj):
        return _url(obj.comprobante, self.context.get('request'))

    def validate_comprobante(self, archivo):
        return validar_archivo_subido(archivo, permitir_pdf=True, max_mb=10, campo='comprobante') if archivo else archivo


class LiquidacionLineaSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True)

    class Meta:
        model = LiquidacionLinea
        fields = ('id', 'unidad', 'unidad_codigo', 'tipo', 'descripcion', 'monto_usd')


class LiquidacionSerializer(serializers.ModelSerializer):
    propietario_nombre = serializers.CharField(source='propietario.nombre', read_only=True)
    lineas = LiquidacionLineaSerializer(many=True, read_only=True)

    class Meta:
        model = Liquidacion
        fields = '__all__'


class GenerarLiquidacionSerializer(serializers.Serializer):
    propietario = serializers.IntegerField()
    periodo = serializers.CharField(max_length=7, required=False, validators=[validar_periodo])
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')


class PagarLiquidacionSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False)
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class ConsultaPropiedadSerializer(serializers.ModelSerializer):
    unidad_codigo = serializers.CharField(source='unidad.codigo', read_only=True, default=None)
    unidad_titulo = serializers.CharField(source='unidad.titulo', read_only=True, default=None)

    class Meta:
        model = ConsultaPropiedad
        fields = '__all__'
        read_only_fields = ('unidad', 'nombre', 'telefono', 'email', 'mensaje')
