"""
Catálogo unificado de productos para POS / inventario.

Las consultas recurrentes (inventario y categorías activas) se cachean en
Redis a nivel de tenant mediante ``apps.core.cache_utils.cached`` para reducir
la carga sobre PostgreSQL. Las claves se invalidan automáticamente desde
``apps.inventario.signals`` cuando un producto, variante o categoría cambia.
"""
from __future__ import annotations

from django.conf import settings
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat

from apps.inventario.models import Producto, Variacionproducto, Categoriaproducto
from apps.core.cache_utils import cached, invalidate_pattern


def _catalogo_key(categoria_id=None) -> tuple:
    """Construye la clave de caché del inventario unificado por categoría."""
    return ("inventario_unificado", str(categoria_id or "todos"))


def _categorias_key() -> tuple:
    """Construye la clave de caché de las categorías activas."""
    return ("categorias_activas",)


@cached(
    ttl=settings.CACHE_TTL.get("catalogo_productos", 300),
    key_builder=_catalogo_key,
)
def obtener_inventario_unificado(categoria_id=None):
    """
    Cruza productos simples y variantes en una sola lista estructurada.

    Devuelve la lista ordenada alfabéticamente. El resultado se cachea en
    Redis por tenant y por categoría.
    """
    # --- Productos Simples ---
    productos_simples_qs = Producto.objects.filter(activo=True, tipo='simple')
    if categoria_id and str(categoria_id).isdigit():
        productos_simples_qs = productos_simples_qs.filter(categoria_id=categoria_id)

    productos_simples = productos_simples_qs.annotate(
        nombre_categoria=F('categoria__nombre'),
        nombre_completo=F('nombre')
    ).values('nombre_completo', 'nombre_categoria', 'codigo_barras', 'cantidad')

    # --- Variantes de Productos ---
    variantes_qs = Variacionproducto.objects.filter(producto__activo=True)
    if categoria_id and str(categoria_id).isdigit():
        variantes_qs = variantes_qs.filter(producto__categoria_id=categoria_id)

    variantes = variantes_qs.select_related('producto', 'producto__categoria').annotate(
        nombre_completo=Concat(
            F('producto__nombre'), Value(' - '), F('nombre'),
            output_field=CharField(),
        ),
        nombre_categoria=F('producto__categoria__nombre'),
    ).values('nombre_completo', 'nombre_categoria', 'codigo_barras', 'cantidad')

    # --- Unir y Ordenar ---
    inventario_completo = list(productos_simples) + list(variantes)
    inventario_ordenado = sorted(
        inventario_completo,
        key=lambda item: item.get('nombre_completo', '').lower(),
    )

    return inventario_ordenado


@cached(
    ttl=settings.CACHE_TTL.get("catalogo_productos", 300),
    key_builder=_categorias_key,
)
def obtener_categorias_activas():
    """Devuelve las categorías activas ordenadas alfabéticamente (cacheado)."""
    return list(
        Categoriaproducto.objects.filter(activo=True)
        .values('id', 'nombre')
        .order_by('nombre')
    )


def invalidar_cache_catalogo() -> None:
    """Invalida las claves de caché del catálogo (productos/variantes/categorías)."""
    invalidate_pattern("inventario_unificado")
    invalidate_pattern("categorias_activas")
