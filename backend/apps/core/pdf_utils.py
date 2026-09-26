"""
Utilidades compartidas para generar PDFs (facturas, notas, recibos de
nómina) con `xhtml2pdf`.
"""
from __future__ import annotations

import base64
import os
from io import BytesIO


# Tamaño máximo de exhibición del logo en los PDFs (ancho, alto) en píxeles.
# `xhtml2pdf` no soporta de forma confiable `max-width`/`max-height` en CSS
# para <img> -- suele ignorarlos y renderizar la imagen a su resolución
# NATIVA. Un logo subido a resolución "para imprimir" (ej. 1500x1500px)
# terminaba ocupando media página de la factura sin importar qué dijera el
# CSS. La solución robusta es reducir el propio archivo de imagen ANTES de
# incrustarlo, no pelear con el motor de PDF.
LOGO_MAX_SIZE = (160, 80)


def obtener_logo_base64(logo_field) -> str | None:
    """
    Devuelve el logo de la empresa como data-URI base64, ya redimensionado
    para que quepa en `LOGO_MAX_SIZE` conservando la proporción.
    """
    if not (logo_field and hasattr(logo_field, 'path') and os.path.exists(logo_field.path)):
        return None

    try:
        from PIL import Image

        with Image.open(logo_field.path) as img:
            img = img.convert('RGBA') if img.mode in ('P', 'LA') else img
            img.thumbnail(LOGO_MAX_SIZE)
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
    except Exception:
        # Si Pillow no puede procesar el archivo (formato raro, corrupto),
        # se cae al comportamiento anterior antes que dejar la factura sin
        # logo -- una imagen sobredimensionada es mejor que ninguna.
        with open(logo_field.path, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
