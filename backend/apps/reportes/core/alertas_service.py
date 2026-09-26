"""
Centro de Alertas: una sola lista, ordenada por urgencia, que junta lo que
YA existe repartido en cada módulo (cuentas por cobrar vencidas, cuentas por
pagar vencidas/por vencer, productos con bajo stock) -- nadie tiene que
entrar a revisar cada reporte por separado para darse cuenta de que algo
necesita atención.

Cada fuente se calcula en su propio try/except: si un módulo falla o no
está configurado para este tenant, las demás alertas igual se muestran --
un error en Cuentas por Pagar nunca debe dejar sin avisar del stock agotado.
"""
from datetime import date, timedelta

DIAS_CXC_ATENCION = 30
DIAS_CXC_URGENTE = 60
DIAS_CXP_POR_VENCER = 7
DIAS_LOTE_ATENCION = 30
DIAS_LOTE_URGENTE = 7
DIAS_RECLAMO_ATENCION = 2
DIAS_RECLAMO_URGENTE = 5
DIAS_GARANTIA_ATENCION = 15
DIAS_GARANTIA_URGENTE = 3

NIVEL_ORDEN = {'urgente': 0, 'atencion': 1}


def _alertas_cuentas_por_cobrar() -> list[dict]:
    from apps.facturacion.services.pagos_service import reporte_cuentas_por_cobrar

    alertas = []
    for fila in reporte_cuentas_por_cobrar():
        for factura in fila['facturas']:
            dias = factura['dias']
            if dias <= DIAS_CXC_ATENCION:
                continue
            nivel = 'urgente' if dias > DIAS_CXC_URGENTE else 'atencion'
            numero_factura = factura['correlativo'] or f"#{factura['id']}"
            alertas.append({
                'tipo': 'cxc',
                'nivel': nivel,
                'titulo': f"{fila['cliente_nombre']} -- {numero_factura}",
                'descripcion': f"${factura['saldo_pendiente_base']} pendiente desde hace {dias} días",
                'link': '/admin/facturacion/cuentas-por-cobrar',
                'dias': dias,
            })
    return alertas


def _alertas_cuentas_por_pagar() -> list[dict]:
    from apps.proveedores.core.proveedores_service import reporte_cuentas_por_pagar

    hoy = date.today()
    alertas = []
    for fila in reporte_cuentas_por_pagar():
        for cuenta in fila['cuentas']:
            fecha_venc_str = cuenta.get('fecha_vencimiento')
            if fecha_venc_str:
                fecha_venc = date.fromisoformat(fecha_venc_str)
                dias_para_vencer = (fecha_venc - hoy).days
                if dias_para_vencer < 0:
                    nivel = 'urgente'
                    descripcion = f"Venció hace {-dias_para_vencer} días"
                elif dias_para_vencer <= DIAS_CXP_POR_VENCER:
                    nivel = 'atencion'
                    descripcion = f"Vence en {dias_para_vencer} días" if dias_para_vencer > 0 else "Vence hoy"
                else:
                    continue
            else:
                if cuenta['dias'] <= DIAS_CXC_URGENTE:
                    continue
                nivel = 'atencion'
                descripcion = f"${cuenta['saldo_pendiente']} pendiente desde hace {cuenta['dias']} días (sin fecha de vencimiento)"
            alertas.append({
                'tipo': 'cxp',
                'nivel': nivel,
                'titulo': f"{fila['proveedor_nombre']} -- {cuenta['numero_documento'] or 's/n'}",
                'descripcion': descripcion,
                'link': '/admin/proveedores/cuentas-por-pagar',
                'dias': cuenta['dias'],
            })
    return alertas


def _alertas_bajo_stock() -> list[dict]:
    from apps.inventario.services.stock_service import obtener_productos_bajo_stock

    alertas = []
    for p in obtener_productos_bajo_stock():
        agotado = (p['cantidad'] or 0) <= 0
        alertas.append({
            'tipo': 'stock',
            'nivel': 'urgente' if agotado else 'atencion',
            'titulo': p['nombre'],
            'descripcion': 'Agotado' if agotado else f"Quedan {p['cantidad']} unidades (mínimo {p['stock_minimo'] or 10})",
            'link': '/admin/inventario',
            'dias': None,
        })
    return alertas


def _alertas_lotes_por_vencer() -> list[dict]:
    from apps.farmacia.models import LoteProducto

    hoy = date.today()
    alertas = []
    lotes = LoteProducto.objects.filter(activo=True, cantidad__gt=0).select_related('producto')
    for lote in lotes:
        dias = (lote.fecha_vencimiento - hoy).days
        if dias > DIAS_LOTE_ATENCION:
            continue
        if dias < 0:
            nivel = 'urgente'
            descripcion = f"Venció hace {-dias} días -- {lote.cantidad} unidades"
        elif dias <= DIAS_LOTE_URGENTE:
            nivel = 'urgente'
            descripcion = ('Vence hoy' if dias == 0 else f"Vence en {dias} días") + f" -- {lote.cantidad} unidades"
        else:
            nivel = 'atencion'
            descripcion = f"Vence en {dias} días -- {lote.cantidad} unidades"
        alertas.append({
            'tipo': 'lote',
            'nivel': nivel,
            'titulo': f"{lote.producto.nombre} -- Lote {lote.numero_lote or 's/n'}",
            'descripcion': descripcion,
            'link': '/admin/farmacia/lotes',
            # Mismo criterio de orden que las demás fuentes ("mayor número =
            # más urgente" dentro de su nivel): un lote ya vencido hace más
            # días pesa más que uno que recién venció; uno por vencer pesa
            # menos mientras más lejos esté esa fecha.
            'dias': -dias,
        })
    return alertas


def _alertas_seguimientos_comerciales() -> list[dict]:
    from apps.crm.models import Oportunidad

    hoy = date.today()
    alertas = []
    oportunidades = Oportunidad.objects.filter(
        proximo_seguimiento__isnull=False, proximo_seguimiento__lte=hoy,
    ).exclude(etapa__in=('ganado', 'perdido'))
    for op in oportunidades:
        dias = (hoy - op.proximo_seguimiento).days
        alertas.append({
            'tipo': 'seguimiento',
            'nivel': 'urgente' if dias > 3 else 'atencion',
            'titulo': f"{op.titulo} -- {op.nombre_contacto}",
            'descripcion': 'Seguimiento vencía hoy' if dias == 0 else f"Seguimiento pendiente desde hace {dias} días",
            'link': '/admin/crm/oportunidades',
            'dias': dias,
        })
    return alertas


def _alertas_reclamos_postventa() -> list[dict]:
    from apps.postventa.models import ReclamoPostventa

    hoy = date.today()
    alertas = []
    reclamos = ReclamoPostventa.objects.filter(estado__in=('abierto', 'en_proceso'))
    for r in reclamos:
        dias = (hoy - r.fecha_apertura.date()).days
        if dias < DIAS_RECLAMO_ATENCION:
            continue
        nivel = 'urgente' if dias >= DIAS_RECLAMO_URGENTE else 'atencion'
        alertas.append({
            'tipo': 'reclamo',
            'nivel': nivel,
            'titulo': f"{r.titulo} -- {r.nombre_contacto}",
            'descripcion': f"Reclamo sin cerrar desde hace {dias} días" if dias > 0 else "Reclamo abierto hoy",
            'link': '/admin/postventa/reclamos',
            'dias': dias,
        })
    return alertas


def _alertas_garantias_por_vencer() -> list[dict]:
    from apps.postventa.models import Garantia

    hoy = date.today()
    alertas = []
    garantias = Garantia.objects.filter(
        fecha_vencimiento__gte=hoy,
        fecha_vencimiento__lte=hoy + timedelta(days=DIAS_GARANTIA_ATENCION),
    ).select_related('producto', 'cliente')
    for g in garantias:
        dias = (g.fecha_vencimiento - hoy).days
        nivel = 'urgente' if dias <= DIAS_GARANTIA_URGENTE else 'atencion'
        nombre_producto = getattr(g.producto, 'nombre', None) or 'Producto'
        nombre_cliente = getattr(g.cliente, 'nombre', None) or 'Cliente'
        alertas.append({
            'tipo': 'garantia',
            'nivel': nivel,
            'titulo': f"{nombre_producto} -- {nombre_cliente}",
            'descripcion': 'La garantía vence hoy' if dias == 0 else f"La garantía vence en {dias} días",
            'link': '/admin/postventa/garantias',
            'dias': -dias,
        })
    return alertas


def obtener_alertas() -> dict:
    alertas: list[dict] = []
    for fuente in (
        _alertas_cuentas_por_cobrar, _alertas_cuentas_por_pagar, _alertas_bajo_stock,
        _alertas_lotes_por_vencer, _alertas_seguimientos_comerciales, _alertas_reclamos_postventa,
        _alertas_garantias_por_vencer,
    ):
        try:
            alertas.extend(fuente())
        except Exception:
            import logging
            logging.getLogger(__name__).warning('No se pudo calcular una fuente del Centro de Alertas: %s', fuente.__name__, exc_info=True)

    alertas.sort(key=lambda a: (NIVEL_ORDEN.get(a['nivel'], 2), -(a['dias'] or 0)))
    return {
        'alertas': alertas,
        'total': len(alertas),
        'urgentes': sum(1 for a in alertas if a['nivel'] == 'urgente'),
    }
