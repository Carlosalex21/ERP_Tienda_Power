"""
Módulos comerciales: qué partes del sistema incluye cada plan.

``Plan.modulos`` guarda la lista de códigos de este catálogo que el plan
incluye (vacío = todos, así los planes creados antes de esta función no
pierden nada). Los códigos son los mismos que usa el panel
(``utils/modulosPanel.ts`` en el frontend) -- si se agrega un módulo allá
que deba poder venderse por separado, hay que agregarlo también aquí.

Los módulos "básicos" del panel (dashboard, alertas, datos de la empresa,
monedas, suscripción...) no están en este catálogo: siempre se incluyen,
sin ellos el sistema no se puede operar.

``rutas_api`` son los prefijos (bajo ``/api/v1/``) que pertenecen SOLO a
ese módulo; ``PlanModulosMiddleware`` los bloquea si el plan no incluye el
módulo. Los endpoints compartidos por varias pantallas (ej. productos, que
usan el POS y el inventario) no se listan: bloquearlos rompería módulos que
sí se pagaron, así que esos módulos solo se ocultan en el panel.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuloComercial:
    codigo: str
    rutas_api: tuple[str, ...] = ()


MODULOS_COMERCIALES: tuple[ModuloComercial, ...] = (
    # Ventas
    ModuloComercial("pos"),
    ModuloComercial("mesas", ("restaurantes/mesas/",)),
    ModuloComercial("cocina"),
    ModuloComercial("ordenes_servicio", ("servicios/ordenes/",)),
    ModuloComercial("pedidos"),
    ModuloComercial("clientes"),
    ModuloComercial("clientes_b2b", ("clientes/b2b/clientes/", "clientes/b2b/niveles-precio/")),
    ModuloComercial("notas_entrega"),
    ModuloComercial("cotizaciones", ("crm/cotizaciones/",)),
    ModuloComercial("oportunidades", ("crm/oportunidades/",)),
    # Inventario
    ModuloComercial("inventario"),
    ModuloComercial("categorias"),
    ModuloComercial("ajustes_inventario", ("inventario/ajustes/",)),
    ModuloComercial("traslados_inventario", ("inventario/traslados/",)),
    ModuloComercial("almacenes"),
    ModuloComercial("lotes_vencimientos", ("farmacia/lotes/",)),
    ModuloComercial("importar_productos", ("inventario/productos/bulk-upload/",)),
    # Compras
    ModuloComercial("proveedores", ("proveedores/proveedores/",)),
    ModuloComercial("ordenes_compra", ("proveedores/ordenes-compra/",)),
    ModuloComercial("cuentas_por_pagar", ("proveedores/cuentas-por-pagar/", "proveedores/reportes/cuentas-por-pagar/")),
    # Finanzas
    ModuloComercial("cobros"),
    ModuloComercial("cuentas_por_cobrar"),
    ModuloComercial("caja_bancos"),
    # Contabilidad
    ModuloComercial("empresas_contables"),
    ModuloComercial("servicios_facturables"),
    ModuloComercial("asientos_contables", ("contabilidad/asientos/", "contabilidad/plantillas/")),
    ModuloComercial("plan_cuentas"),
    ModuloComercial("libro_mayor", ("contabilidad/reportes/libro-mayor/",)),
    ModuloComercial("balance_comprobacion", ("contabilidad/reportes/balance-comprobacion/",)),
    ModuloComercial("estados_financieros", ("contabilidad/reportes/estados-financieros/",)),
    ModuloComercial("conciliacion_bancaria", ("contabilidad/conciliacion-bancaria/",)),
    # Fiscal
    ModuloComercial("libros_fiscales", ("facturacion/libro-compra-venta/",)),
    ModuloComercial("notas_credito", ("facturacion/notas-credito/",)),
    ModuloComercial("notas_debito", ("facturacion/notas-debito/",)),
    ModuloComercial("retenciones", ("facturacion/retenciones/",)),
    # Recursos humanos
    ModuloComercial("empleados"),
    ModuloComercial("departamentos"),
    ModuloComercial("nomina", ("rrhh/nomina/", "rrhh/conceptos-nomina/", "rrhh/recibo-nomina/")),
    # Postventa
    ModuloComercial("garantias", ("postventa/garantias/",)),
    ModuloComercial("reclamos_postventa", ("postventa/reclamos/",)),
    # Análisis y extras
    ModuloComercial("reportes", ("reportes/ventas/", "reportes/analitica/", "reportes/clientes/")),
    ModuloComercial("auditoria", ("auditoria/",)),
    ModuloComercial("pagos_online"),
    ModuloComercial("importar_clientes", ("clientes/bulk-upload/",)),
    ModuloComercial("importar_clientes_b2b", ("clientes/b2b/bulk-upload/",)),
)

CODIGOS_MODULOS: frozenset[str] = frozenset(m.codigo for m in MODULOS_COMERCIALES)

_PREFIJO_API = "/api/v1/"

# (prefijo, código), del más largo al más corto: gana el más específico.
_RUTAS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((_PREFIJO_API + ruta, m.codigo) for m in MODULOS_COMERCIALES for ruta in m.rutas_api),
        key=lambda par: len(par[0]),
        reverse=True,
    )
)


def modulo_de_ruta(path: str) -> str | None:
    """Código del módulo dueño exclusivo de ``path`` (o ``None`` si es compartida/básica)."""
    # Enlaces públicos (cotización compartida, cuenta de mesa por QR...) los
    # usan los clientes finales del negocio: nunca se bloquean por plan.
    if "/publico/" in path or "/publica/" in path:
        return None
    for prefijo, codigo in _RUTAS:
        if path.startswith(prefijo):
            return codigo
    return None


def modulos_del_plan(plan) -> frozenset[str] | None:
    """Módulos que incluye ``plan``; ``None`` = todos (plan sin restricción o sin plan)."""
    if plan is None or not plan.modulos:
        return None
    return frozenset(plan.modulos)
