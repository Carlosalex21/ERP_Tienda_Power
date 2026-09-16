"""Serializers del catálogo público (sin autenticación)."""
from decimal import Decimal

from rest_framework import serializers

from apps.inventario.services.stock_service import calcular_stock_disponible
from apps.pagos.models import MetodoPagoConfig, PagoMovilConfig, ZelleConfig
from apps.configuracion.models import ConfiguracionEmpresa

_CENT = Decimal("0.01")


class PublicOrderItemSerializer(serializers.Serializer):
    # Coincide con el `id` que expone `PublicProductoSerializer`: hoy el
    # catálogo público solo lista productos simples (`Producto`), no
    # variantes -- ver nota en `PublicProductoSerializer`.
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)


class PublicCreateOrderSerializer(serializers.Serializer):
    """Valida los datos de un nuevo pedido creado por un cliente final."""
    cliente_nombre = serializers.CharField(max_length=100)
    cliente_telefono = serializers.CharField(max_length=20)
    cliente_direccion = serializers.CharField(max_length=255, required=False)
    items = PublicOrderItemSerializer(many=True, min_length=1)
    # Pago manual (Pago Móvil / Zelle): opcionales -- un pedido puede llegar
    # sin referencia todavía (el cliente paga y confirma después por
    # WhatsApp/teléfono). Si vienen, se registra de una vez la transacción
    # de pasarela para que el admin no tenga que cruzar datos a mano.
    metodo_pago_config_id = serializers.IntegerField(required=False, allow_null=True)
    referencia_pago = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PublicPagoMovilConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoMovilConfig
        fields = ('banco', 'cedula', 'telefono')


class PublicZelleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZelleConfig
        fields = ('email_zelle', 'nombre_beneficiario')


class PublicMetodoPagoConfigSerializer(serializers.ModelSerializer):
    """
    Métodos de pago visibles para el cliente final en el checkout del
    catálogo público. Solo expone lo necesario para que el cliente sepa a
    dónde/cómo pagar -- nunca datos internos del tenant (ninguna clave de
    Stripe se expone aquí; el backend la usa server-side al crear la sesión).
    """
    pago_movil_config = PublicPagoMovilConfigSerializer(read_only=True)
    zelle_config = PublicZelleConfigSerializer(read_only=True)
    es_stripe = serializers.SerializerMethodField()

    class Meta:
        model = MetodoPagoConfig
        fields = ('id', 'nombre', 'instrucciones', 'pago_movil_config', 'zelle_config', 'es_stripe')

    def get_es_stripe(self, obj):
        return hasattr(obj, 'stripe_config')


class PublicEmpresaInfoSerializer(serializers.ModelSerializer):
    """
    Datos mínimos y seguros de la empresa para el storefront público -- solo
    lo que un visitante anónimo necesita (nombre y teléfono de contacto).
    Nunca expone RIF, razón social o dirección fiscal.
    """
    class Meta:
        model = ConfiguracionEmpresa
        fields = ('nombre_comercial', 'telefono')


class PublicProductoSerializer(serializers.Serializer):
    """
    Representación de un `Producto` en el catálogo público.

    Nota: solo cubre productos simples. `Variacionproducto` no se expone
    todavía en el catálogo público (y `Reservastock` tampoco lo soporta a
    nivel de variante) -- es la limitación conocida a resolver si un tenant
    necesita vender variantes (talla/color) en su tienda pública.
    """
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    precio_venta = serializers.DecimalField(max_digits=10, decimal_places=2, source='precio')
    base_imponible = serializers.SerializerMethodField()
    iva_monto = serializers.SerializerMethodField()
    iva_porcentaje = serializers.SerializerMethodField()
    moneda_codigo = serializers.SerializerMethodField()
    moneda_simbolo = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()
    imagen_url = serializers.SerializerMethodField()

    def get_moneda_codigo(self, obj):
        moneda = obj.moneda or self._moneda_base()
        return moneda.codigo if moneda else None

    def get_moneda_simbolo(self, obj):
        moneda = obj.moneda or self._moneda_base()
        return (moneda.simbolo or moneda.codigo) if moneda else None

    def _moneda_base(self):
        # `precio_venta` de un producto sin `moneda` asignada se interpreta
        # como la moneda base del tenant (ver `Producto.moneda`) -- cacheado
        # en la instancia del serializer para no repetir la consulta por
        # cada producto de la página.
        if not hasattr(self, '_moneda_base_cache'):
            from apps.configuracion.services.conversion_service import (
                get_moneda_base, MonedaNoEncontradaError,
            )
            try:
                self._moneda_base_cache = get_moneda_base()
            except MonedaNoEncontradaError:
                self._moneda_base_cache = None
        return self._moneda_base_cache

    def get_base_imponible(self, obj):
        if obj.base_imponible is None:
            return None
        return str(Decimal(obj.base_imponible).quantize(_CENT))

    def get_iva_monto(self, obj):
        if obj.precio is None or obj.base_imponible is None:
            return None
        return str((Decimal(obj.precio) - Decimal(obj.base_imponible)).quantize(_CENT))

    def get_iva_porcentaje(self, obj):
        return float(obj.configuracion_iva.porcentaje_iva) if obj.configuracion_iva else 0

    def get_stock_disponible(self, obj):
        return calcular_stock_disponible(obj)

    def get_imagen_url(self, obj):
        request = self.context.get('request')
        if obj.imagen and hasattr(obj.imagen, 'url'):
            return request.build_absolute_uri(obj.imagen.url)
        return None
