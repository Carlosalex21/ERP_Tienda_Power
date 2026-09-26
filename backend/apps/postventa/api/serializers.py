from rest_framework import serializers

from ..models import Garantia, ReclamoPostventa


class GarantiaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True, default=None)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    cliente_telefono = serializers.CharField(source='cliente.telefono', read_only=True, default=None)
    factura_correlativo = serializers.CharField(source='factura.correlativo', read_only=True, default=None)
    esta_vigente = serializers.BooleanField(read_only=True)
    tiene_reclamo_abierto = serializers.SerializerMethodField()

    class Meta:
        model = Garantia
        fields = (
            'id', 'detalle_factura', 'factura', 'factura_correlativo', 'producto', 'producto_nombre',
            'cliente', 'cliente_nombre', 'cliente_telefono', 'fecha_inicio', 'fecha_vencimiento', 'meses_garantia',
            'esta_vigente', 'tiene_reclamo_abierto', 'fecha_creacion',
        )

    def get_tiene_reclamo_abierto(self, obj):
        return obj.reclamos.filter(estado__in=['abierto', 'en_proceso']).exists()


class ReclamoPostventaSerializer(serializers.ModelSerializer):
    nombre_contacto = serializers.CharField(read_only=True)
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True, default=None)
    factura_correlativo = serializers.CharField(source='factura.correlativo', read_only=True, default=None)
    usuario_asignado_nombre = serializers.SerializerMethodField()
    garantia_vigente = serializers.SerializerMethodField()

    class Meta:
        model = ReclamoPostventa
        fields = (
            'id', 'garantia', 'garantia_vigente', 'factura', 'factura_correlativo', 'producto', 'producto_nombre',
            'cliente', 'nombre_contacto_libre', 'telefono_contacto', 'nombre_contacto',
            'titulo', 'descripcion', 'estado', 'prioridad', 'usuario_asignado', 'usuario_asignado_nombre',
            'resolucion', 'fecha_apertura', 'fecha_actualizacion', 'fecha_cierre',
        )
        read_only_fields = ('estado', 'resolucion', 'fecha_apertura', 'fecha_actualizacion', 'fecha_cierre')

    def get_usuario_asignado_nombre(self, obj):
        if not obj.usuario_asignado:
            return None
        return obj.usuario_asignado.get_full_name() or obj.usuario_asignado.username

    def get_garantia_vigente(self, obj):
        return obj.garantia.esta_vigente if obj.garantia_id else None


class CrearReclamoSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=150)
    descripcion = serializers.CharField(required=False, allow_blank=True)
    cliente = serializers.IntegerField(required=False, allow_null=True)
    nombre_contacto_libre = serializers.CharField(required=False, allow_blank=True, max_length=150)
    telefono_contacto = serializers.CharField(required=False, allow_blank=True, max_length=30)
    factura = serializers.IntegerField(required=False, allow_null=True)
    producto = serializers.IntegerField(required=False, allow_null=True)
    garantia = serializers.IntegerField(required=False, allow_null=True)
    prioridad = serializers.ChoiceField(choices=[c[0] for c in ReclamoPostventa.PRIORIDAD_CHOICES], default='media')


class CambiarEstadoReclamoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=[c[0] for c in ReclamoPostventa.ESTADO_CHOICES])
    resolucion = serializers.CharField(required=False, allow_blank=True)
