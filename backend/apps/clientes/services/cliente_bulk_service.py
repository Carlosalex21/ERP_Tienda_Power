"""
Carga masiva de Clientes (retail) desde CSV/Excel.

Corre de forma síncrona -- ver el mismo razonamiento en
``apps.inventario.services.product_service.procesar_carga_masiva_productos``:
sin envío de correos ni otro trabajo lento de por medio, no hay ninguna
razón para pasar esto por Celery. El admin ve el resultado completo
(creados/actualizados/errores por fila) en la misma respuesta.
"""
import io
import math

import pandas as pd
from django.db import transaction

from ..models import Cliente

TIPOS_DOCUMENTO_VALIDOS = {choice[0] for choice in Cliente.TIPO_DOCUMENTO_CHOICES}


class ClienteBulkUploadError(Exception):
    """Excepción controlada durante la carga masiva de clientes."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []


def _texto(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and math.isnan(value):
        return ''
    texto = str(value).strip()
    return '' if texto.lower() == 'nan' else texto


@transaction.atomic
def procesar_carga_masiva_clientes(file_content: bytes, file_name: str) -> dict:
    """
    Procesa un archivo (CSV o Excel) para la creación/actualización masiva
    de Clientes (retail).

    Columnas reconocidas: `nombre` (obligatoria); `telefono`, `email`,
    `tipo_documento` (V/E/J/G/P), `documento` y `direccion` (opcionales).

    El emparejamiento para actualizar en vez de duplicar usa, en orden,
    `telefono`, `email` o (`tipo_documento` + `documento`) -- si la fila no
    trae ninguno, se crea un cliente nuevo.

    Returns:
        dict: ``{total_filas, clientes_creados, clientes_actualizados, errores}``.
    """
    try:
        if file_name.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content), dtype=str, keep_default_na=False)
        elif file_name.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content), dtype=str)
            df = df.fillna('')
        else:
            raise ClienteBulkUploadError("Formato de archivo no soportado. Usa .csv o .xlsx.")
    except ClienteBulkUploadError:
        raise
    except Exception as e:
        raise ClienteBulkUploadError(f"Error al leer el archivo: {e}")

    if len(df) == 0:
        raise ClienteBulkUploadError("El archivo no tiene filas de datos.")

    df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]

    if 'nombre' not in df.columns:
        raise ClienteBulkUploadError("Falta la columna obligatoria: nombre.")

    clientes_creados = 0
    clientes_actualizados = 0
    errores_detalle = []

    for index, row in df.iterrows():
        fila = index + 2  # +2: la fila 1 es el encabezado, pandas es 0-indexado.
        nombre = _texto(row.get('nombre'))
        if not nombre:
            errores_detalle.append({"fila": fila, "error": "Falta el nombre del cliente."})
            continue

        telefono = _texto(row.get('telefono')) or None
        email = _texto(row.get('email')) or None
        documento = _texto(row.get('documento')) or None
        tipo_documento = _texto(row.get('tipo_documento')).upper() or None
        if tipo_documento and tipo_documento not in TIPOS_DOCUMENTO_VALIDOS:
            errores_detalle.append({
                "fila": fila,
                "error": f"tipo_documento '{tipo_documento}' inválido (usa uno de: {', '.join(sorted(TIPOS_DOCUMENTO_VALIDOS))}).",
            })
            continue

        cliente_data = {
            'nombre': nombre,
            'email': email,
            'direccion': _texto(row.get('direccion')),
            'tipo_documento': tipo_documento,
            'documento': documento,
        }

        try:
            with transaction.atomic():
                if telefono:
                    cliente_data['telefono'] = telefono
                    cliente, created = Cliente.objects.update_or_create(telefono=telefono, defaults=cliente_data)
                elif email:
                    cliente, created = Cliente.objects.update_or_create(email=email, defaults=cliente_data)
                elif tipo_documento and documento:
                    cliente, created = Cliente.objects.update_or_create(
                        tipo_documento=tipo_documento, documento=documento, defaults=cliente_data,
                    )
                else:
                    cliente = Cliente.objects.create(**cliente_data)
                    created = True
            if created:
                clientes_creados += 1
            else:
                clientes_actualizados += 1
        except Exception as e:
            errores_detalle.append({"fila": fila, "error": str(e)})

    return {
        "total_filas": len(df),
        "clientes_creados": clientes_creados,
        "clientes_actualizados": clientes_actualizados,
        "errores": errores_detalle,
    }
