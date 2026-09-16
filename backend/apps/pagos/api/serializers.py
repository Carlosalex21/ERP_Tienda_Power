from rest_framework import serializers
from ..models import Banco, MetodoPagoConfig, PagoMovilConfig, ZelleConfig, StripeConfig, TransaccionPasarela


class BancoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banco
        fields = ('id', 'nombre', 'activo')


class PagoMovilConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoMovilConfig
        fields = '__all__'

class ZelleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZelleConfig
        fields = '__all__'


class StripeConfigSerializer(serializers.ModelSerializer):
    """
    ``secret_key``/``webhook_secret`` son ``write_only``: una vez guardadas,
    la API nunca las vuelve a mostrar (ni siquiera al propio admin del
    tenant) -- evita que queden expuestas en logs de red o en el DevTools
    de cualquiera que abra el panel. ``tiene_secret_key`` indica si ya hay
    una configurada sin revelar el valor.
    """
    secret_key = serializers.CharField(write_only=True)
    webhook_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    tiene_secret_key = serializers.SerializerMethodField()
    modo_test = serializers.BooleanField(read_only=True)

    class Meta:
        model = StripeConfig
        fields = (
            'id', 'metodo_pago', 'publishable_key', 'secret_key',
            'webhook_secret', 'moneda', 'tiene_secret_key', 'modo_test',
        )

    def get_tiene_secret_key(self, obj):
        return bool(obj.secret_key)


class MetodoPagoConfigSerializer(serializers.ModelSerializer):
    pago_movil_config = PagoMovilConfigSerializer(read_only=True)
    zelle_config = ZelleConfigSerializer(read_only=True)
    stripe_config = StripeConfigSerializer(read_only=True)

    class Meta:
        model = MetodoPagoConfig
        fields = ('id', 'nombre', 'activo', 'es_manual', 'instrucciones', 'pago_movil_config', 'zelle_config', 'stripe_config')

class TransaccionPasarelaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)

    class Meta:
        model = TransaccionPasarela
        fields = ('id', 'factura', 'metodo_pago', 'metodo_pago_nombre', 'monto', 'referencia_externa', 'estado', 'fecha_creacion')
        read_only_fields = ('id', 'fecha_creacion', 'metodo_pago_nombre')