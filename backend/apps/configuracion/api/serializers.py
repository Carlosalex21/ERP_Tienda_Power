"""
Serializers de la app de configuración.

Incluye IVA, tipos de documento fiscal, configuración de empresa y los
nuevos módulos de **multi-moneda** (Moneda, TasaCambio).
"""
from __future__ import annotations

from rest_framework import serializers

from ..models import (
    ConfiguracionEmpresa,
    Configuracioniva,
    Moneda,
    TasaCambio,
    Tipodocumentofiscal,
)


class ConfiguracionEmpresaSerializer(serializers.ModelSerializer):
    """Serializer de la configuración de la empresa del tenant."""

    # Solo escritura -- el PIN nunca se devuelve (ni siquiera hasheado) en
    # ninguna respuesta. Vacío/ausente = no tocar el PIN ya guardado.
    pin = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ConfiguracionEmpresa
        fields = (
            "nombre_comercial",
            "razon_social",
            "rif",
            "telefono",
            "direccion",
            "logo",
            "requiere_pin_eliminar",
            "pin",
            "mensaje_whatsapp_venta",
        )

    def update(self, instance, validated_data):
        pin = validated_data.pop('pin', None)
        instance = super().update(instance, validated_data)
        if pin:
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                raise serializers.ValidationError({"pin": "El PIN debe tener entre 4 y 6 dígitos numéricos."})
            from ..services.pin_service import establecer_pin
            establecer_pin(pin)
        return instance


class IvaSerializer(serializers.ModelSerializer):
    """Serializer de la configuración de IVA."""

    class Meta:
        model = Configuracioniva
        fields = "__all__"


class TipoDocumentoSerializer(serializers.ModelSerializer):
    """Serializer de tipos de documento fiscal."""

    class Meta:
        model = Tipodocumentofiscal
        fields = "__all__"


class MonedaSerializer(serializers.ModelSerializer):
    """Serializer de moneda (ISO 4217)."""

    codigo = serializers.CharField(max_length=3, allow_blank=False, trim_whitespace=True)

    class Meta:
        model = Moneda
        fields = ("id", "codigo", "nombre", "simbolo", "es_predeterminada", "activa", "fecha_creacion")
        read_only_fields = ("id", "fecha_creacion")

    def validate(self, attrs):
        codigo = attrs.get("codigo", getattr(self.instance, "codigo", "") or "").upper()
        attrs["codigo"] = codigo
        if not codigo or len(codigo) != 3:
            raise serializers.ValidationError({"codigo": "El código debe ser ISO 4217 (3 letras)."})
        return attrs


class TasaCambioSerializer(serializers.ModelSerializer):
    """Serializer de tasas de cambio con historial."""

    codigo_moneda = serializers.CharField(source="moneda.codigo", read_only=True)
    nombre_moneda = serializers.CharField(source="moneda.nombre", read_only=True)

    class Meta:
        model = TasaCambio
        fields = (
            "id",
            "moneda",
            "codigo_moneda",
            "nombre_moneda",
            "fecha",
            "tasa",
            "fuente",
            "activa",
        )
        read_only_fields = ("id", "fecha")

    def validate(self, attrs):
        tasa = attrs.get("tasa")
        if tasa is not None and tasa <= 0:
            raise serializers.ValidationError({"tasa": "La tasa debe ser mayor que cero."})
        return attrs
