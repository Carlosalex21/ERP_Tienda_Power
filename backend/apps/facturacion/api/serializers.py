"""
Serializers de la app de facturación.

Incluye facturas (con campos SENIAT y multi-moneda), detalles, métodos de
pago, transacciones, cupones, devoluciones y los nuevos documentos fiscales:
notas de crédito, notas de débito, libros de compra/venta y retenciones.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.configuracion.models import ConfiguracionCorrelativo
from apps.inventario.models import Producto, Variacionproducto

from apps.facturacion.models import (
    Cupondescuento,
    Detallefactura,
    Devolucion,
    Factura,
    LibroCompraVenta,
    MetodoPago,
    NotaCredito,
    NotaDebito,
    Retencion,
    Transaccionpago,
)
from apps.facturacion.services.calculos_service import recalcular_y_guardar_factura


class MetodoPagoSerializer(serializers.ModelSerializer):
    """Serializer de método de pago."""

    banco_nombre = serializers.CharField(source="banco.nombre", read_only=True, default=None)

    class Meta:
        model = MetodoPago
        fields = "__all__"


class DetallefacturaSerializer(serializers.ModelSerializer):
    """Serializer de lectura de detalle de factura (con nombre resuelto)."""

    nombre = serializers.SerializerMethodField()

    class Meta:
        model = Detallefactura
        fields = (
            "id",
            "nombre",
            "cantidad",
            "precio_unitario",
            "descuento",
            "subtotal_linea",
            "iva_linea",
            "total_linea",
            "producto",
            "variante",
        )

    def get_nombre(self, obj):
        if obj.variante is not None:
            return f"{obj.producto.nombre} ({obj.variante.nombre})"
        return obj.producto.nombre


class DetallefacturaWriteSerializer(serializers.ModelSerializer):
    """Serializer de escritura de detalle de factura."""

    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    variante = serializers.PrimaryKeyRelatedField(
        queryset=Variacionproducto.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Detallefactura
        fields = ("producto", "variante", "cantidad", "precio_unitario", "descuento")


class FacturaSerializer(serializers.ModelSerializer):
    """Serializer de factura con campos SENIAT y multi-moneda."""

    detalles = DetallefacturaSerializer(many=True, read_only=True)
    detalles_para_crear = DetallefacturaWriteSerializer(
        many=True, write_only=True, source="detalles"
    )
    moneda_codigo = serializers.CharField(source="moneda.codigo", read_only=True, default=None)
    moneda_nombre = serializers.CharField(source="moneda.nombre", read_only=True, default=None)
    vendedor_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Factura
        fields = (
            "id",
            "usuario",
            "vendedor",
            "vendedor_nombre",
            "condicion_pago",
            "cliente",
            "orden",
            "fecha_operacion",
            "correlativo",
            "numero_control",
            "base_imponible",
            "retencion_total",
            "moneda",
            "moneda_codigo",
            "moneda_nombre",
            "tasa_cambio",
            "subtotal",
            "descuento_global",
            "iva_total",
            "total",
            "subtotal_base",
            "base_imponible_base",
            "iva_base",
            "retencion_base",
            "total_base",
            "almacen",
            "estado",
            "metodo_pago",
            "nif_factura",
            "activo",
            "nombre_cliente_pendiente",
            "comentario_pendiente",
            "detalles",
            "detalles_para_crear",
        )

    def get_vendedor_nombre(self, obj):
        persona = obj.vendedor or obj.usuario
        if not persona:
            return None
        return persona.get_full_name() or persona.username
        read_only_fields = (
            "subtotal",
            "base_imponible",
            "iva_total",
            "retencion_total",
            "total",
            "subtotal_base",
            "base_imponible_base",
            "iva_base",
            "retencion_base",
            "total_base",
            "correlativo",
            "numero_control",
        )

    def create(self, validated_data):
        detalles_data = validated_data.pop("detalles", [])
        factura = Factura.objects.create(**validated_data)
        for detalle_data in detalles_data:
            Detallefactura.objects.create(factura=factura, **detalle_data)
        recalcular_y_guardar_factura(factura)
        # El registro en el Libro de Ventas ya NO se dispara aquí -- se
        # mueve a `Factura.save()` (ver ese método), porque en este punto
        # (creación desde el panel/POS) la factura normalmente todavía está
        # en estado 'borrador', sin correlativo asignado. Registrarla aquí
        # metía en el Libro Fiscal ventas que ni siquiera se habían pagado
        # todavía, con un número de documento vacío.
        return factura

    def update(self, instance, validated_data):
        detalles_data = validated_data.pop("detalles", None)
        instance = super().update(instance, validated_data)
        if detalles_data is not None:
            instance.detalles.all().delete()
            for detalle_data in detalles_data:
                Detallefactura.objects.create(factura=instance, **detalle_data)
            recalcular_y_guardar_factura(instance)
            # Idem: `Factura.save()` (llamado dentro de `recalcular_y_guardar_factura`)
            # ya deja la línea del Libro al día si la factura tiene correlativo.
        return instance


class TransaccionpagoSerializer(serializers.ModelSerializer):
    """Serializer de transacción de pago."""

    metodo_pago_nombre = serializers.CharField(source="metodo_pago.nombre", read_only=True, default=None)

    class Meta:
        model = Transaccionpago
        fields = "__all__"


class ConfiguracionCorrelativoReadSerializer(serializers.ModelSerializer):
    """Serializer de lectura de la configuración de correlativo."""

    class Meta:
        model = ConfiguracionCorrelativo
        fields = ["prefijo", "current_number", "number_length"]


class ConfiguracionCorrelativoWriteSerializer(serializers.ModelSerializer):
    """Serializer de escritura de la configuración de correlativo."""

    password = serializers.CharField(write_only=True)

    class Meta:
        model = ConfiguracionCorrelativo
        fields = ["prefijo", "current_number", "number_length", "password"]


class CupondescuentoSerializer(serializers.ModelSerializer):
    """Serializer de cupón de descuento."""

    class Meta:
        model = Cupondescuento
        fields = "__all__"


class DevolucionSerializer(serializers.ModelSerializer):
    """Serializer de devolución."""

    class Meta:
        model = Devolucion
        fields = "__all__"


class NotaCreditoSerializer(serializers.ModelSerializer):
    """
    Serializer de nota de crédito (SENIAT).

    El cliente envía ``factura``, ``monto`` y ``motivo``. Los campos
    ``numero_nota``, ``numero_control``, ``base_imponible``, ``iva_total``,
    ``retencion_total`` y ``total`` los calcula el servicio
    ``crear_nota_credito``.
    """

    monto = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True,
        help_text="Monto a acreditar sobre la factura (no puede exceder el total).",
    )
    # base_imponible/iva_total/retencion_total/total se calculan proporcionales
    # a los campos EN MONEDA PROPIA de la factura (no a los `_base`), así que
    # están en la misma moneda en que se emitió esa factura -- este campo le
    # dice al frontend cuál es, para que nunca la etiquete con la moneda
    # equivocada (el mismo bug que hubo en Pedidos y en el Libro de Ventas).
    factura_moneda_codigo = serializers.CharField(source="factura.moneda_codigo", read_only=True, default=None)

    class Meta:
        model = NotaCredito
        fields = (
            "id",
            "factura",
            "factura_moneda_codigo",
            "numero_nota",
            "numero_control",
            "fecha_emision",
            "motivo",
            "monto",
            "base_imponible",
            "iva_total",
            "retencion_total",
            "total",
            "base_imponible_base",
            "iva_base",
            "retencion_base",
            "total_base",
            "activo",
        )
        read_only_fields = (
            "fecha_emision",
            "numero_nota",
            "numero_control",
            "base_imponible",
            "iva_total",
            "retencion_total",
            "total",
            "base_imponible_base",
            "iva_base",
            "retencion_base",
            "total_base",
        )


class NotaDebitoSerializer(serializers.ModelSerializer):
    """
    Serializer de nota de débito (SENIAT).

    El cliente envía ``factura``, ``monto`` y ``motivo``. El servicio
    ``crear_nota_debito`` calcula ``numero_nota``, ``numero_control``,
    ``base_imponible``, ``iva_total`` y ``total``.
    """

    monto = serializers.DecimalField(
        max_digits=10, decimal_places=2, write_only=True,
        help_text="Monto a debitar sobre la factura (recargo, interés, diferencia).",
    )
    # Ver el mismo comentario en NotaCreditoSerializer.
    factura_moneda_codigo = serializers.CharField(source="factura.moneda_codigo", read_only=True, default=None)

    class Meta:
        model = NotaDebito
        fields = (
            "id",
            "factura",
            "factura_moneda_codigo",
            "numero_nota",
            "numero_control",
            "fecha_emision",
            "motivo",
            "monto",
            "base_imponible",
            "iva_total",
            "total",
            "base_imponible_base",
            "iva_base",
            "total_base",
            "activo",
        )
        read_only_fields = (
            "fecha_emision",
            "numero_nota",
            "numero_control",
            "base_imponible",
            "iva_total",
            "total",
            "base_imponible_base",
            "iva_base",
            "total_base",
        )


class LibroCompraVentaSerializer(serializers.ModelSerializer):
    """Serializer del libro de compras y ventas (SENIAT)."""

    class Meta:
        model = LibroCompraVenta
        fields = "__all__"


class RetencionSerializer(serializers.ModelSerializer):
    """
    Serializer del comprobante de retención (SENIAT).

    El cliente envía ``factura``/``proveedor``, ``tipo_retencion``,
    ``porcentaje`` y ``base``. El ``monto`` lo calcula
    ``crear_comprobante_retencion`` a partir de base y porcentaje.
    """

    # `base` es un monto que el usuario tipea a mano al crear el
    # comprobante (no se deriva de la factura), así que puede estar en
    # cualquier moneda -- normalmente la de la factura asociada, cuando hay
    # una. Se expone para que el frontend pueda etiquetarlo honestamente en
    # vez de asumir una moneda fija.
    factura_moneda_codigo = serializers.CharField(source="factura.moneda_codigo", read_only=True, default=None)

    class Meta:
        model = Retencion
        fields = "__all__"
        read_only_fields = ("fecha_emision", "numero_comprobante", "monto")
