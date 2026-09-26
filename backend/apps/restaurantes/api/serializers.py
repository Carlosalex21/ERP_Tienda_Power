from decimal import Decimal

from rest_framework import serializers

from ..models import Mesa, PedidoMesa, PedidoMesaItem, PushSubscription


class MesaSerializer(serializers.ModelSerializer):
    estado = serializers.SerializerMethodField()
    pedido_abierto_id = serializers.SerializerMethodField()
    # Para que la grilla de mesas (que no tiene abierto el modal del pedido)
    # pueda mostrar una alerta visible/sonora cuando alguien llama al mesero
    # o pide la cuenta -- antes solo se veía si el mesero ya había abierto
    # esa mesa puntual, así que una llamada real podía pasar desapercibida.
    mesero_solicitado = serializers.SerializerMethodField()
    cuenta_solicitada = serializers.SerializerMethodField()

    class Meta:
        model = Mesa
        fields = ('id', 'numero', 'capacidad', 'activo', 'estado', 'pedido_abierto_id', 'mesero_solicitado', 'cuenta_solicitada')

    def get_estado(self, obj):
        return 'ocupada' if obj.pedido_abierto else 'libre'

    def get_pedido_abierto_id(self, obj):
        pedido = obj.pedido_abierto
        return pedido.id if pedido else None

    def get_mesero_solicitado(self, obj):
        pedido = obj.pedido_abierto
        return bool(pedido and pedido.mesero_solicitado)

    def get_cuenta_solicitada(self, obj):
        pedido = obj.pedido_abierto
        return bool(pedido and pedido.cuenta_solicitada)


class PedidoMesaItemSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True, default=None)
    preparado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PedidoMesaItem
        fields = (
            'id', 'producto', 'producto_nombre', 'cantidad', 'precio_unitario', 'notas', 'subtotal',
            'persona_asignada', 'preparado', 'departamento', 'departamento_nombre',
            'preparado_por_nombre', 'fecha_preparado',
        )
        read_only_fields = ('precio_unitario', 'departamento', 'preparado_por_nombre', 'fecha_preparado')

    def get_preparado_por_nombre(self, obj):
        if not obj.preparado_por:
            return None
        return obj.preparado_por.get_full_name() or obj.preparado_por.username


class PedidoMesaSerializer(serializers.ModelSerializer):
    """Detalle de un pedido de mesa para el panel (requiere sesión)."""

    mesa_numero = serializers.CharField(source='mesa.numero', read_only=True)
    mesero_nombre = serializers.SerializerMethodField()
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, default=None)
    items = PedidoMesaItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PedidoMesa
        fields = (
            'id', 'mesa', 'mesa_numero', 'mesero', 'mesero_nombre', 'cliente', 'cliente_nombre',
            'estado', 'factura', 'token_publico', 'division_personas', 'propina_pct',
            'mesero_solicitado', 'cuenta_solicitada', 'fecha_apertura', 'fecha_cierre',
            'items', 'total', 'comprobante_pago',
        )
        read_only_fields = ('estado', 'factura', 'token_publico', 'fecha_apertura', 'fecha_cierre')

    def get_mesero_nombre(self, obj):
        if not obj.mesero:
            return None
        return obj.mesero.get_full_name() or obj.mesero.username

    def get_total(self, obj):
        return str(sum((item.subtotal for item in obj.items.all()), start=0))


class AgregarItemSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, default=1)
    notas = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CerrarPedidoSerializer(serializers.Serializer):
    metodo_pago_id = serializers.IntegerField()
    condicion_pago = serializers.ChoiceField(choices=('contado', 'credito'), default='contado')
    moneda_id = serializers.IntegerField(required=False, allow_null=True)
    # Opcional -- el mesero puede no saber quién es el cliente hasta el
    # momento de cobrar; si lo elige aquí, queda en la Factura resultante
    # (antes SIEMPRE quedaba sin cliente, porque solo se podía asignar al
    # abrir la mesa y ninguna pantalla lo pedía en ese momento).
    cliente_id = serializers.IntegerField(required=False, allow_null=True)


class PedidoMesaPublicoSerializer(serializers.ModelSerializer):
    """
    Lo que ve un comensal al escanear el QR de la mesa -- sin datos internos
    (nada de costos, nombre del mesero, ID de cliente interno, etc.), solo
    lo necesario para revisar el pedido y dividir la cuenta.
    """

    mesa_numero = serializers.CharField(source='mesa.numero', read_only=True)
    items = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    desglose_por_persona = serializers.SerializerMethodField()
    # `pin_anfitrion` JAMÁS se expone -- si viajara en esta respuesta,
    # cualquiera que vea la cuenta (todo el grupo) podría leerlo y
    # sobreescribir los datos de pago de otra persona, exactamente lo que
    # el PIN existe para evitar. Solo se usa server-side para comparar.
    tiene_pin_anfitrion = serializers.SerializerMethodField()

    class Meta:
        model = PedidoMesa
        fields = (
            'mesa_numero', 'estado', 'items', 'total',
            'division_personas', 'propina_pct', 'mesero_solicitado', 'cuenta_solicitada',
            'datos_pago_anfitrion', 'tiene_pin_anfitrion', 'comprobante_pago', 'desglose_por_persona',
        )

    def get_items(self, obj):
        return [
            {
                'id': item.id,
                'nombre': item.producto.nombre,
                'cantidad': item.cantidad,
                'precio_unitario': str(item.precio_unitario),
                'subtotal': str(item.subtotal),
                'persona_asignada': item.persona_asignada,
                'preparado': item.preparado,
            }
            for item in obj.items.select_related('producto').all()
        ]

    def get_total(self, obj):
        return str(sum((item.subtotal for item in obj.items.all()), start=0))

    def get_tiene_pin_anfitrion(self, obj):
        return bool(obj.pin_anfitrion)

    def get_desglose_por_persona(self, obj):
        """
        Reparte cada ítem entre la persona a la que se asignó (ver
        `persona_asignada`) -- lo que no se asignó a nadie se reparte por
        igual entre TODAS las personas, así que si nadie usa la asignación
        por ítem, el resultado es idéntico a la división pareja de siempre
        (compatible hacia atrás).
        """
        items = list(obj.items.all())
        n = max(obj.division_personas, 1)
        propina_pct = obj.propina_pct / Decimal('100')

        subtotal_sin_asignar = sum(
            (item.subtotal for item in items if not item.persona_asignada), start=Decimal('0'),
        )
        parte_comun = subtotal_sin_asignar / n

        desglose = []
        for persona in range(1, n + 1):
            subtotal_propio = sum(
                (item.subtotal for item in items if item.persona_asignada == persona), start=Decimal('0'),
            )
            subtotal_persona = subtotal_propio + parte_comun
            desglose.append({
                'persona': persona,
                'subtotal': str(subtotal_persona.quantize(Decimal('0.01'))),
                'total_con_propina': str((subtotal_persona * (1 + propina_pct)).quantize(Decimal('0.01'))),
            })
        return desglose


class ActualizarDivisionSerializer(serializers.Serializer):
    """Lo que cualquiera que escaneó el QR puede ajustar -- estado compartido por mesa."""

    division_personas = serializers.IntegerField(min_value=1, required=False)
    propina_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal('0'), max_value=Decimal('100'), required=False,
    )
    datos_pago_anfitrion = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    # Si ya existe un PIN (`pedido.pin_anfitrion`), hay que mandar el mismo
    # aquí para poder tocar `datos_pago_anfitrion` -- si todavía no existe,
    # ESTE valor se guarda como el PIN nuevo (ver `PedidoMesaPublicoView.patch`).
    pin_anfitrion = serializers.RegexField(r'^\d{4}$', required=False)


class AsignarPersonaItemSerializer(serializers.Serializer):
    """A cuál de las N personas que dividen la cuenta corresponde un ítem (o ninguna = compartido)."""

    item_id = serializers.IntegerField()
    persona_asignada = serializers.IntegerField(min_value=1, allow_null=True)


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ('endpoint', 'p256dh', 'auth')
