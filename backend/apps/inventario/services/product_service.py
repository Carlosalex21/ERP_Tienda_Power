import pandas as pd
import io
from django.db import transaction
from ..models import Producto, Categoriaproducto, Productocategoria

class ProductBulkUploadError(Exception):
    """Excepción personalizada para errores durante la carga masiva de productos."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []

@transaction.atomic
def procesar_carga_masiva_productos(file_content: bytes, file_name: str):
    """
    Procesa un archivo (CSV o Excel) para la creación/actualización masiva de Productos.
    Esta función se ejecuta dentro del contexto de un tenant.

    Args:
        file_content (bytes): El contenido del archivo en bytes.
        file_name (str): El nombre original del archivo para determinar el formato.

    Returns:
        dict: Un diccionario con el resumen del proceso.
    """
    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif file_name.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise ProductBulkUploadError("Formato de archivo no soportado.")
    except Exception as e:
        raise ProductBulkUploadError(f"Error al leer el archivo: {e}")

    df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]

    required_columns = {'nombre', 'codigo_barras', 'precio_venta'}
    if not required_columns.issubset(df.columns):
        missing = required_columns - set(df.columns)
        raise ProductBulkUploadError(f"Faltan las siguientes columnas obligatorias: {', '.join(missing)}")

    productos_creados = 0
    productos_actualizados = 0
    errores_detalle = []

    for index, row in df.iterrows():
        codigo_barras = str(row.get('codigo_barras', '')).strip()
        nombre = row.get('nombre')

        if not codigo_barras or not nombre:
            errores_detalle.append({"fila": index + 2, "error": "Faltan datos obligatorios (nombre, codigo_barras)."})
            continue

        product_data = {
            'nombre': nombre,
            'precio_venta': pd.to_numeric(row.get('precio_venta'), errors='coerce') or 0.00,
            'precio_compra': pd.to_numeric(row.get('precio_compra'), errors='coerce') or 0.00,
            'cantidad': pd.to_numeric(row.get('stock_inicial'), errors='coerce') or 0,
            'descripcion': str(row.get('descripcion', ''))
        }

        try:
            producto, created = Producto.objects.update_or_create(
                codigo_barras=codigo_barras,
                defaults=product_data
            )
            if created:
                productos_creados += 1
            else:
                productos_actualizados += 1

        except Exception as e:
            errores_detalle.append({"fila": index + 2, "codigo_barras": codigo_barras, "error": str(e)})

    return {
        "total_filas": len(df),
        "productos_creados": productos_creados,
        "productos_actualizados": productos_actualizados,
        "errores": errores_detalle,
    }