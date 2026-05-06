# apps/inventario/core/catalog_service.py
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat
from erp.models import Producto, Variacionproducto, Categoriaproducto

def obtener_inventario_unificado(categoria_id=None):
    """
    Cruza productos simples y variantes en una sola lista estructurada.
    Devuelve la lista ordenada alfabéticamente.
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
        nombre_completo=Concat(F('producto__nombre'), Value(' - '), F('nombre'), output_field=CharField()),
        nombre_categoria=F('producto__categoria__nombre')
    ).values('nombre_completo', 'nombre_categoria', 'codigo_barras', 'cantidad')
    
    # --- Unir y Ordenar ---
    inventario_completo = list(productos_simples) + list(variantes)
    inventario_ordenado = sorted(
        inventario_completo, 
        key=lambda item: item.get('nombre_completo', '').lower()
    )
    
    return inventario_ordenado

def obtener_categorias_activas():
    return list(Categoriaproducto.objects.filter(activo=True).values('id', 'nombre').order_by('nombre'))