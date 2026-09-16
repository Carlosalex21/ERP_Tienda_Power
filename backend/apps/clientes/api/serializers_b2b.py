from rest_framework import serializers
from ..models import ClienteB2B, NivelPrecio
from ..services.pricing_service import calcular_precio_efectivo
from apps.inventario.services.stock_service import calcular_stock_disponible

class ClienteB2BBulkUploadSerializer(serializers.Serializer):
    """
    Serializer para validar el archivo subido para la carga masiva de clientes B2B.
    """
    file = serializers.FileField(help_text="Archivo CSV o Excel (.xlsx) con los clientes a importar.")

    def validate_file(self, value):
        """
        Valida la extensión del archivo.
        """
        if not value.name.endswith('.csv') and not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("El archivo debe ser de tipo CSV o Excel (.xlsx).")
        return value

class B2BAccountActivationSerializer(serializers.Serializer):
    """
    Serializer para activar una cuenta B2B y establecer la contraseña.
    """
    token = serializers.UUIDField(required=True, help_text="Token de invitación recibido por correo.")
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="La nueva contraseña para la cuenta.")
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'}, help_text="Confirmación de la contraseña.")

    def validate(self, data):
        """
        Verifica que las contraseñas coincidan.
        """
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        # Aquí se podrían añadir validadores de fortaleza de contraseña si se desea.
        return data

class NivelPrecioB2BSerializer(serializers.ModelSerializer):
    """
    Serializer para mostrar la información del Nivel de Precio de un cliente B2B.
    """
    class Meta:
        model = NivelPrecio
        fields = ('id', 'nombre', 'porcentaje_descuento', 'monto_minimo_periodo')


class B2BVarianteSerializer(serializers.Serializer):
    """
    Variante/SKU de un producto 'variable' vista por un cliente B2B: precio
    y stock son los de LA VARIANTE, no los del producto padre (antes el
    catálogo B2B no distinguía variantes -- ver `b2b_order_service`).
    """
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    sku = serializers.CharField(allow_null=True)
    precio_lista = serializers.DecimalField(max_digits=10, decimal_places=2, source='precio')
    precio_con_descuento = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()

    def get_precio_con_descuento(self, obj):
        cliente_b2b = self.context.get('cliente_b2b')
        return calcular_precio_efectivo(obj, cliente_b2b)

    def get_stock_disponible(self, obj):
        return obj.cantidad or 0


class B2BProductoSerializer(serializers.Serializer):
    """
    Producto visto por un cliente B2B autenticado: incluye el precio de
    lista y el precio efectivo tras aplicar el descuento de su NivelPrecio
    (ver ``pricing_service.calcular_precio_efectivo``).
    """
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    tipo = serializers.CharField()
    precio_lista = serializers.DecimalField(max_digits=10, decimal_places=2, source='precio')
    precio_con_descuento = serializers.SerializerMethodField()
    stock_disponible = serializers.SerializerMethodField()
    variantes = serializers.SerializerMethodField()

    def get_precio_con_descuento(self, obj):
        if obj.tipo == 'variable':
            return None
        cliente_b2b = self.context.get('cliente_b2b')
        return calcular_precio_efectivo(obj, cliente_b2b)

    def get_stock_disponible(self, obj):
        if obj.tipo == 'variable':
            return None
        return calcular_stock_disponible(obj)

    def get_variantes(self, obj):
        if obj.tipo != 'variable':
            return []
        variantes = obj.variacionproducto_set.all()
        return B2BVarianteSerializer(variantes, many=True, context=self.context).data


class B2BOrderItemSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    variante_id = serializers.IntegerField(required=False, allow_null=True)
    cantidad = serializers.IntegerField(min_value=1)


class B2BCreateOrderSerializer(serializers.Serializer):
    """Valida los datos de un nuevo pedido creado por un cliente B2B autenticado."""
    items = B2BOrderItemSerializer(many=True, min_length=1)


class ProximoNivelSerializer(serializers.Serializer):
    nivel = NivelPrecioB2BSerializer()
    monto_faltante = serializers.DecimalField(max_digits=12, decimal_places=2)


class ClienteB2BProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para exponer el perfil de un cliente B2B autenticado,
    incluyendo su progreso de nivel de precio y su línea de crédito.
    """
    nivel_precio = NivelPrecioB2BSerializer(read_only=True)
    total_comprado_periodo = serializers.SerializerMethodField()
    proximo_nivel = serializers.SerializerMethodField()
    credito_usado = serializers.SerializerMethodField()
    credito_disponible = serializers.SerializerMethodField()

    class Meta:
        model = ClienteB2B
        fields = (
            'razon_social',
            'rif',
            'email_contacto',
            'telefono_contacto',
            'nivel_precio',
            'nivel_precio_actualizado_en',
            'total_comprado_periodo',
            'proximo_nivel',
            'limite_credito',
            'credito_usado',
            'credito_disponible',
            'estado',
        )

    def get_total_comprado_periodo(self, obj):
        from ..services.pricing_tier_service import total_comprado_periodo
        return total_comprado_periodo(obj)

    def get_proximo_nivel(self, obj):
        from ..services.pricing_tier_service import proximo_nivel
        info = proximo_nivel(obj)
        return ProximoNivelSerializer(info).data if info else None

    def get_credito_usado(self, obj):
        from ..services.credit_service import credito_usado
        return credito_usado(obj)

    def get_credito_disponible(self, obj):
        from ..services.credit_service import credito_disponible
        return credito_disponible(obj)


class SugerenciaReposicionSerializer(serializers.Serializer):
    """Ver `apps.clientes.services.reposicion_service`."""
    producto_id = serializers.IntegerField(source='producto.id')
    producto_nombre = serializers.CharField(source='producto.nombre')
    cantidad_habitual = serializers.IntegerField()
    dias_entre_pedidos = serializers.FloatField()
    ultima_compra = serializers.DateField()
    dias_estimados_restantes = serializers.IntegerField()
    urgente = serializers.BooleanField()


class NivelPrecioAdminSerializer(serializers.ModelSerializer):
    """CRUD de niveles de precio para el admin del tenant."""
    class Meta:
        model = NivelPrecio
        fields = ('id', 'nombre', 'porcentaje_descuento', 'monto_minimo_periodo', 'activo')


class ClienteB2BAdminSerializer(serializers.ModelSerializer):
    """
    Vista/edición de un cliente B2B para el admin del tenant: puede ajustar
    el nivel de precio, la línea de crédito y el estado; no puede tocar
    `user` (se gestiona solo por el flujo de invitación/activación).
    """
    nivel_precio_nombre = serializers.CharField(source='nivel_precio.nombre', read_only=True)
    total_comprado_periodo = serializers.SerializerMethodField()
    credito_usado = serializers.SerializerMethodField()

    class Meta:
        model = ClienteB2B
        fields = (
            'id', 'razon_social', 'rif', 'email_contacto', 'telefono_contacto', 'direccion_fiscal',
            'nivel_precio', 'nivel_precio_nombre', 'nivel_precio_actualizado_en',
            'total_comprado_periodo', 'limite_credito', 'credito_usado', 'estado',
            'fecha_creacion',
        )
        read_only_fields = ('fecha_creacion', 'nivel_precio_actualizado_en')

    def get_total_comprado_periodo(self, obj):
        from ..services.pricing_tier_service import total_comprado_periodo
        return total_comprado_periodo(obj)

    def get_credito_usado(self, obj):
        from ..services.credit_service import credito_usado
        return credito_usado(obj)