"""
Carga masiva de Productos desde CSV/Excel.

Corre de forma SÍNCRONA (no Celery/segundo plano): para el volumen típico
de un catálogo (cientos a unos pocos miles de filas), procesar el archivo
dentro de la misma petición HTTP y devolver el resultado completo
(creados/actualizados/errores por fila) es más simple y más confiable que
un job en segundo plano -- no depende de que haya un worker de Celery
corriendo (si no lo hay, el endpoint simplemente no funcionaba), y el
admin ve de inmediato si de verdad funcionó, en vez de un "procesando..."
que nunca confirma nada (el resultado solo quedaba en un `print()` del
worker, invisible para el usuario).
"""
import io
import math
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction

from ..models import Producto, Categoriaproducto


class ProductBulkUploadError(Exception):
    """Excepción controlada durante la carga masiva de productos."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def _num(value, default=None):
    """
    Convierte una celda a `Decimal` de forma segura.

    Antes esto se hacía con `pd.to_numeric(...) or 0.00`: si la celda no
    era numérica, `pd.to_numeric(..., errors='coerce')` devolvía `NaN`, y
    `NaN or 0.00` sigue siendo `NaN` (un `float` no-cero es "truthy" en
    Python) -- ese `NaN` se colaba tal cual a un `DecimalField`, reventando
    el guardado de esa fila con un error críptico en vez de uno claro.
    """
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    texto = str(value).strip()
    if not texto or texto.lower() == 'nan':
        return default
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return default


def _texto(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and math.isnan(value):
        return ''
    texto = str(value).strip()
    return '' if texto.lower() == 'nan' else texto


@transaction.atomic
def procesar_carga_masiva_productos(file_content: bytes, file_name: str) -> dict:
    """
    Procesa un archivo (CSV o Excel) para la creación/actualización masiva
    de Productos.

    Columnas reconocidas: `nombre` y `precio` (obligatorias -- `precio` es
    el precio final YA CON IVA incluido, la misma convención que usa todo
    el sistema); `codigo_barras`, `sku`, `stock_inicial`, `descripcion`,
    `categoria` (se crea si no existe) e `iva` (nombre de una configuración
    de IVA ya existente) son opcionales.

    El emparejamiento para actualizar en vez de duplicar usa, en orden,
    `codigo_barras` o `sku` -- si la fila no trae ninguno de los dos (un
    rubro que no usa código de barras), simplemente se crea un producto
    nuevo, igual que al crear uno a mano sin esos campos.

    Returns:
        dict: ``{total_filas, productos_creados, productos_actualizados, errores}``.
    """
    try:
        if file_name.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content), dtype=str, keep_default_na=False)
        elif file_name.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)
            df = df.fillna('')
        else:
            raise ProductBulkUploadError("Formato de archivo no soportado. Usa .csv o .xlsx.")
    except ProductBulkUploadError:
        raise
    except Exception as e:
        raise ProductBulkUploadError(f"Error al leer el archivo: {e}")

    if len(df) == 0:
        raise ProductBulkUploadError("El archivo no tiene filas de datos.")

    df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]

    # Acepta tanto `precio` como el histórico `precio_venta` -- pero el
    # modelo real (`Producto.precio`) es un único campo, no una base y un
    # precio de venta separados.
    columna_precio = 'precio' if 'precio' in df.columns else ('precio_venta' if 'precio_venta' in df.columns else None)
    faltantes = [c for c, ok in (('nombre', 'nombre' in df.columns), ('precio', columna_precio is not None)) if not ok]
    if faltantes:
        raise ProductBulkUploadError(f"Faltan las siguientes columnas obligatorias: {', '.join(faltantes)}")

    from apps.configuracion.models import Configuracioniva
    from apps.configuracion.services.conversion_service import get_moneda_base, MonedaNoEncontradaError

    categorias_cache: dict[str, Categoriaproducto] = {}
    ivas_cache: dict[str, Configuracioniva | None] = {}
    try:
        moneda_base = get_moneda_base()
    except MonedaNoEncontradaError:
        moneda_base = None

    productos_creados = 0
    productos_actualizados = 0
    errores_detalle = []

    for index, row in df.iterrows():
        fila = index + 2  # +2: la fila 1 es el encabezado, pandas es 0-indexado.
        nombre = _texto(row.get('nombre'))
        if not nombre:
            errores_detalle.append({"fila": fila, "error": "Falta el nombre del producto."})
            continue

        precio = _num(row.get(columna_precio))
        if precio is None:
            errores_detalle.append({"fila": fila, "error": f"'{columna_precio}' no es un número válido."})
            continue

        codigo_barras = _texto(row.get('codigo_barras')) or None
        sku = _texto(row.get('sku')) or None
        cantidad = _num(row.get('stock_inicial'), default=Decimal('0')) or Decimal('0')

        producto_data = {
            'nombre': nombre,
            'precio': precio,
            'cantidad': int(cantidad),
            'descripcion': _texto(row.get('descripcion')),
            'sku': sku,
        }
        if moneda_base is not None:
            producto_data['moneda'] = moneda_base

        categoria_nombre = _texto(row.get('categoria'))
        if categoria_nombre:
            clave = categoria_nombre.lower()
            categoria = categorias_cache.get(clave)
            if categoria is None:
                categoria = Categoriaproducto.objects.filter(nombre__iexact=categoria_nombre).first()
                if categoria is None:
                    categoria = Categoriaproducto.objects.create(nombre=categoria_nombre)
                categorias_cache[clave] = categoria
            producto_data['categoria'] = categoria

        iva_nombre = _texto(row.get('iva')) or _texto(row.get('impuesto'))
        if iva_nombre:
            clave = iva_nombre.lower()
            if clave not in ivas_cache:
                ivas_cache[clave] = Configuracioniva.objects.filter(nombre__iexact=iva_nombre).first()
            iva = ivas_cache[clave]
            if iva is not None:
                producto_data['configuracion_iva'] = iva
            else:
                errores_detalle.append({
                    "fila": fila, "codigo_barras": codigo_barras,
                    "error": f"No existe un impuesto llamado '{iva_nombre}' -- el producto se guardó sin IVA asignado.",
                })

        try:
            with transaction.atomic():
                if codigo_barras:
                    producto, created = Producto.objects.update_or_create(codigo_barras=codigo_barras, defaults=producto_data)
                elif sku:
                    producto, created = Producto.objects.update_or_create(sku=sku, defaults=producto_data)
                else:
                    producto = Producto.objects.create(**producto_data)
                    created = True
            if created:
                productos_creados += 1
            else:
                productos_actualizados += 1
        except Exception as e:
            errores_detalle.append({"fila": fila, "codigo_barras": codigo_barras, "error": str(e)})

    return {
        "total_filas": len(df),
        "productos_creados": productos_creados,
        "productos_actualizados": productos_actualizados,
        "errores": errores_detalle,
    }
