"""
Integración con Stripe Checkout para cobrar pedidos del catálogo público en
moneda extranjera (tarjetas internacionales).

Cada tenant conecta su propia cuenta de Stripe (``StripeConfig``): no hay
Stripe Connect/OAuth aquí, así que las claves usadas en cada llamada son
siempre las del tenant actual, nunca una clave global de la plataforma.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import stripe

from ..models import MetodoPagoConfig, StripeConfig, TransaccionPasarela

logger = logging.getLogger(__name__)


class StripeNoConfiguradoError(Exception):
    """El tenant no tiene Stripe activo/configurado."""


def obtener_stripe_config_activo() -> StripeConfig:
    """Devuelve la config de Stripe activa del tenant, o lanza si no hay ninguna."""
    config = StripeConfig.objects.select_related('metodo_pago').filter(metodo_pago__activo=True).first()
    if not config:
        raise StripeNoConfiguradoError("Este comercio no tiene Stripe configurado.")
    return config


def crear_checkout_session(factura, success_url: str, cancel_url: str) -> str:
    """
    Crea una Stripe Checkout Session para el total de ``factura`` y registra
    una ``TransaccionPasarela`` en 'pendiente' con el ID de sesión como
    referencia -- el webhook la busca por ese ID cuando Stripe confirma el
    pago.

    Devuelve la URL de Stripe a la que redirigir al cliente.
    """
    config = obtener_stripe_config_activo()
    stripe.api_key = config.secret_key

    monto_centavos = int((factura.total or Decimal('0')) * 100)
    session = stripe.checkout.Session.create(
        mode='payment',
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': config.moneda,
                'unit_amount': monto_centavos,
                'product_data': {'name': f'Pedido {factura.correlativo or factura.id}'},
            },
            'quantity': 1,
        }],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'factura_id': str(factura.id)},
    )

    TransaccionPasarela.objects.create(
        factura=factura,
        metodo_pago=config.metodo_pago,
        monto=factura.total,
        referencia_externa=session.id,
        estado='pendiente',
    )

    return session.url


def procesar_webhook(payload: bytes, sig_header: str) -> None:
    """
    Verifica la firma del webhook y, si el evento es un pago completado,
    marca la ``TransaccionPasarela`` y la ``Factura`` asociadas como pagadas.

    Esto es lo que hace que Stripe sea mejor que el flujo manual: el pago se
    confirma solo, sin que el admin tenga que revisar nada.
    """
    config = obtener_stripe_config_activo()
    if not config.webhook_secret:
        raise StripeNoConfiguradoError("Falta configurar el Webhook Signing Secret de Stripe.")

    event = stripe.Webhook.construct_event(payload, sig_header, config.webhook_secret)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        transaccion = TransaccionPasarela.objects.select_related('factura').filter(
            referencia_externa=session['id'],
        ).first()
        if not transaccion:
            logger.warning("Webhook de Stripe: no se encontró transacción para session %s", session['id'])
            return

        transaccion.estado = 'completado'
        transaccion.save(update_fields=['estado', 'fecha_actualizacion'])

        if transaccion.factura:
            transaccion.factura.estado = 'pagado'
            transaccion.factura.save(update_fields=['estado'])
