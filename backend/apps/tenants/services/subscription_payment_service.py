"""
Cobro de suscripciones SaaS: el dinero fluye del dueño de un tenant HACIA
la plataforma (Carlos), nunca al revés. No confundir con `apps.pagos`, que
es la pasarela que cada TENANT usa para cobrarle a SUS PROPIOS clientes
finales en el catálogo público -- son direcciones de dinero opuestas.

Venezuela paga de forma manual (Pago Móvil/Zelle a la cuenta de la
plataforma) y un superadmin confirma el pago a mano, igual que ya se hace
con los pedidos del catálogo público. El resto de países paga con Stripe
Checkout contra la cuenta de Stripe de LA PLATAFORMA (no una por tenant) y
la confirmación es automática vía webhook.
"""
from __future__ import annotations

from decimal import Decimal

import stripe
from django.utils import timezone

from apps.tenants.models import Client, Plan, PlatformPaymentConfig, Referido, SubscriptionPayment
from apps.tenants.services.subscription_service import SubscriptionService

# Países que pagan de forma manual (Pago Móvil/Zelle). El resto paga con Stripe.
PAISES_PAGO_MANUAL = {'VE'}

METODOS_PAGO_MANUAL = {'pago_movil', 'zelle'}

# Períodos de facturación disponibles: cuántos meses de `plan.precio` se
# cobran, cuántos días de vigencia otorga la suscripción, y el descuento
# aplicado sobre el total (el mismo 20% anual que ya mostraba `planes/page.tsx`
# de forma puramente visual -- aquí pasa a ser la fuente real de verdad que
# tanto el cobro como el frontend consultan).
PERIODOS_SUSCRIPCION = {
    'mensual': {'nombre': 'Mensual', 'meses': 1, 'dias': 30, 'descuento_pct': 0},
    'trimestral': {'nombre': 'Trimestral', 'meses': 3, 'dias': 90, 'descuento_pct': 10},
    'anual': {'nombre': 'Anual', 'meses': 12, 'dias': 365, 'descuento_pct': 20},
}


class PagoSuscripcionError(Exception):
    """Error controlado al crear o confirmar un pago de suscripción."""


class StripePlataformaNoConfiguradoError(PagoSuscripcionError):
    """La plataforma todavía no cargó sus propias credenciales de Stripe."""


def calcular_monto_periodo(precio_mensual: Decimal, periodo: str) -> Decimal:
    """Calcula el monto a cobrar por un período, aplicando el descuento del período."""
    info = PERIODOS_SUSCRIPCION.get(periodo)
    if info is None:
        raise PagoSuscripcionError(f"Período de facturación inválido: {periodo}")
    bruto = Decimal(precio_mensual) * info['meses']
    descuento = bruto * (Decimal(info['descuento_pct']) / Decimal(100))
    return (bruto - descuento).quantize(Decimal('0.01'))


def obtener_config_pago_plataforma() -> PlatformPaymentConfig:
    config, _ = PlatformPaymentConfig.objects.get_or_create(pk=1)
    return config


def metodo_esperado_para_pais(pais_codigo: str) -> str:
    """País de Venezuela paga manual; el resto, con Stripe."""
    return 'manual' if pais_codigo in PAISES_PAGO_MANUAL else 'stripe'


def crear_pago_suscripcion(
    client: Client,
    plan: Plan,
    metodo: str,
    referencia: str = '',
    periodo: str = 'mensual',
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> tuple[SubscriptionPayment, str | None]:
    """
    Crea un `SubscriptionPayment` pendiente. Si el método es Stripe, además
    crea la Checkout Session contra la cuenta de la PLATAFORMA y devuelve su
    URL para redirigir al dueño del tenant.

    Returns:
        (pago, checkout_url) -- checkout_url es None para métodos manuales.
    """
    if metodo not in dict(SubscriptionPayment.METODO_CHOICES):
        raise PagoSuscripcionError(f"Método de pago inválido: {metodo}")
    if periodo not in PERIODOS_SUSCRIPCION:
        raise PagoSuscripcionError(f"Período de facturación inválido: {periodo}")

    es_manual_esperado = metodo_esperado_para_pais(client.pais_codigo) == 'manual'
    if es_manual_esperado and metodo not in METODOS_PAGO_MANUAL:
        raise PagoSuscripcionError(
            "Este país paga la suscripción de forma manual (Pago Móvil o Zelle)."
        )
    if not es_manual_esperado and metodo != 'stripe':
        raise PagoSuscripcionError("Este país paga la suscripción con tarjeta (Stripe).")

    # El plan debe corresponder al módulo con el que se registró el negocio:
    # un restaurante solo renueva planes de restaurante. Se valida aquí (y no
    # solo filtrando la lista en el frontend) porque ambos flujos de pago --
    # dueño en el dominio raíz y admin desde el panel -- pasan por esta función.
    if not plan.aplica_a(client.tipo_negocio):
        raise PagoSuscripcionError("Este plan no está disponible para el tipo de negocio de tu cuenta.")

    monto = calcular_monto_periodo(plan.precio, periodo)

    pago = SubscriptionPayment.objects.create(
        client=client,
        plan=plan,
        periodo=periodo,
        monto=monto,
        metodo=metodo,
        referencia=referencia or '',
    )

    if metodo != 'stripe':
        return pago, None

    config = obtener_config_pago_plataforma()
    if not config.stripe_secret_key:
        raise StripePlataformaNoConfiguradoError(
            "La plataforma aún no configuró su cuenta de Stripe. Contacta al administrador."
        )

    periodo_nombre = PERIODOS_SUSCRIPCION[periodo]['nombre']
    stripe.api_key = config.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode='payment',
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': f"Suscripción {plan.nombre} ({periodo_nombre}) - {client.nombre_empresa}"},
                'unit_amount': int(monto * 100),
            },
            'quantity': 1,
        }],
        success_url=success_url or 'http://localhost:3000/pago?stripe=success',
        cancel_url=cancel_url or 'http://localhost:3000/pago?stripe=cancel',
        client_reference_id=str(pago.id),
        metadata={'subscription_payment_id': str(pago.id)},
    )
    pago.stripe_session_id = session.id
    pago.save(update_fields=['stripe_session_id'])
    return pago, session.url


def confirmar_pago(pago_id: int, admin_user=None, notas: str = '') -> SubscriptionPayment:
    """Confirma un pago pendiente y activa/renueva la suscripción del cliente."""
    pago = SubscriptionPayment.objects.select_related('client', 'plan').get(id=pago_id)
    if pago.estado != 'pendiente':
        raise PagoSuscripcionError(f"El pago ya fue procesado (estado actual: {pago.estado}).")

    pago.estado = 'confirmado'
    pago.fecha_confirmacion = timezone.now()
    pago.confirmado_por = admin_user
    if notas:
        pago.notas = notas
    pago.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por', 'notas'])

    duration_days = PERIODOS_SUSCRIPCION.get(pago.periodo, PERIODOS_SUSCRIPCION['mensual'])['dias']
    SubscriptionService.create_subscription(
        client_id=pago.client_id, plan_id=pago.plan_id, duration_days=duration_days,
    )
    _recompensar_referido_si_aplica(pago.client_id)
    return pago


def _recompensar_referido_si_aplica(client_id: int) -> None:
    """
    Si `client_id` fue invitado por otro tenant (ver `Referido`) y esta es
    la primera vez que confirma un pago real, regala `meses_bonus` de
    suscripción gratis A AMBOS (referente y referido). El `estado` del
    `Referido` pasa a 'recompensado' de una vez, así que renovaciones
    futuras de este mismo cliente nunca vuelven a disparar la recompensa.

    Aislado con try/except: un fallo aquí jamás debe poder tumbar la
    confirmación de un pago real, que ya se guardó antes de llegar a esto.
    """
    try:
        referido = Referido.objects.select_related('referente').get(referido_id=client_id, estado='pendiente')
    except Referido.DoesNotExist:
        return
    try:
        SubscriptionService.otorgar_meses_bonus(referido.referente_id, referido.meses_bonus)
        SubscriptionService.otorgar_meses_bonus(referido.referido_id, referido.meses_bonus)
        referido.estado = 'recompensado'
        referido.fecha_recompensa = timezone.now()
        referido.save(update_fields=['estado', 'fecha_recompensa'])
    except Exception:
        import logging
        logging.getLogger(__name__).warning('No se pudo otorgar la recompensa de referido para el tenant %s', client_id, exc_info=True)


def rechazar_pago(pago_id: int, admin_user=None, motivo: str = '') -> SubscriptionPayment:
    pago = SubscriptionPayment.objects.get(id=pago_id)
    if pago.estado != 'pendiente':
        raise PagoSuscripcionError(f"El pago ya fue procesado (estado actual: {pago.estado}).")

    pago.estado = 'rechazado'
    pago.fecha_confirmacion = timezone.now()
    pago.confirmado_por = admin_user
    pago.notas = motivo
    pago.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por', 'notas'])
    return pago


def procesar_webhook_stripe(payload: bytes, sig_header: str) -> None:
    """Verifica la firma del webhook de Stripe y confirma el pago asociado."""
    config = obtener_config_pago_plataforma()
    if not config.stripe_webhook_secret:
        raise StripePlataformaNoConfiguradoError("Falta configurar el webhook secret de Stripe.")

    event = stripe.Webhook.construct_event(payload, sig_header, config.stripe_webhook_secret)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.get('id')
        try:
            pago = SubscriptionPayment.objects.get(stripe_session_id=session_id)
        except SubscriptionPayment.DoesNotExist:
            return
        if pago.estado == 'pendiente':
            confirmar_pago(pago.id, admin_user=None, notas='Confirmado automáticamente por webhook de Stripe.')
