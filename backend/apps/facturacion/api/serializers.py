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
from apps.facturacion.services.libros_service import registrar_factura_en_libro


class MetodoPagoSerializer(serializers.ModelSerializer):
    """Serializer de método de pago."""

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

    class Meta:
        model = Factura
        fields = (
            "id",
            "usuario",
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
        # Registro automático en el Libro de Venta (SENIAT).
        registrar_factura_en_libro(factura)
        return factura

    def update(self, instance, validated_data):
        detalles_data = validated_data.pop("detalles", None)
        instance = super().update(instance, validated_data)
        if detalles_data is not None:
            instance.detalles.all().delete()
            for detalle_data in detalles_data:
                Detallefactura.objects.create(factura=instance, **detalle_data)
            recalcular_y_guardar_factura(instance)
            # Actualizar el registro en el Libro de Venta (SENIAT).
            from apps.facturacion.models import LibroCompraVenta
            LibroCompraVenta.objects.filter(
                tipo_documento="Factura", numero_documento=instance.correlativo or ""
            ).delete()
            registrar_factura_en_libro(instance)
        return instance


class TransaccionpagoSerializer(serializers.ModelSerializer):
    """Serializer de transacción de pago."""

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

    class Meta:
        model = NotaCredito
        fields = (
            "id",
            "factura",
            "numero_nota",
            "numero_control",
            "fecha_emision",
            "motivo",
            "monto",
            "base_imponible",
            "iva_total",
            "retencion_total",
            "total",
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

    class Meta:
        model = NotaDebito
        fields = (
            "id",
            "factura",
            "numero_nota",
            "numero_control",
            "fecha_emision",
            "motivo",
            "monto",
            "base_imponible",
            "iva_total",
            "total",
            "activo",
        )
        read_only_fields = (
            "fecha_emision",
            "numero_nota",
            "numero_control",
            "base_imponible",
            "iva_total",
            "total",
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

    class Meta:
        model = Retencion
        fields = "__all__"
        read_only_fields = ("fecha_emision", "numero_comprobante", "monto")
