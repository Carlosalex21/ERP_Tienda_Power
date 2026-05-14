from rest_framework import serializers
from .models import MetodoPagoConfig, PagoMovilConfig, ZelleConfig, TransaccionPasarela

class PagoMovilConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoMovilConfig
        fields = '__all__'

class ZelleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ZelleConfig
        fields = '__all__'

class MetodoPagoConfigSerializer(serializers.ModelSerializer):
    pago_movil_config = PagoMovilConfigSerializer(read_only=True)
    zelle_config = ZelleConfigSerializer(read_only=True)

    class Meta:
        model = MetodoPagoConfig
        fields = ('id', 'nombre', 'activo', 'es_manual', 'instrucciones', 'pago_movil_config', 'zelle_config')

class TransaccionPasarelaSerializer(serializers.ModelSerializer):
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True)

    class Meta:
        model = TransaccionPasarela
        fields = ('id', 'factura', 'metodo_pago', 'metodo_pago_nombre', 'monto', 'referencia_externa', 'estado', 'fecha_creacion')
        read_only_fields = ('id', 'fecha_creacion', 'metodo_pago_nombre')