"""
Validación de archivos subidos por usuarios (o por comensales, en los
endpoints públicos con QR).

Un `ImageField`/`FileField` NO valida nada cuando la vista asigna
`request.FILES[...]` directo al modelo y hace `save()`: acepta cualquier
tipo y tamaño. Aquí se revisa lo mínimo indispensable antes de guardar:

- tamaño máximo,
- extensión permitida,
- contenido real (no solo la extensión ni el `Content-Type` que declara el
  cliente, que son triviales de falsificar): las imágenes se abren con
  Pillow y los PDF deben empezar con la firma `%PDF-`.
"""
from __future__ import annotations

import os

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

EXT_IMAGEN = {'.jpg', '.jpeg', '.png', '.webp'}
EXT_PDF = {'.pdf'}
MAX_PIXELES = 40_000_000  # evita "bombas de descompresión" (imagen diminuta en disco, gigante en memoria)


def validar_archivo_subido(archivo, *, permitir_pdf: bool = False, max_mb: int = 5, campo: str = 'archivo'):
    """Lanza `ValidationError` (400, mensaje legible) si el archivo no es seguro; devuelve el archivo si lo es."""
    if archivo is None:
        raise serializers.ValidationError({campo: 'No se recibió ningún archivo.'})

    if archivo.size > max_mb * 1024 * 1024:
        raise serializers.ValidationError({campo: f'El archivo es muy pesado (máximo {max_mb} MB).'})
    if archivo.size == 0:
        raise serializers.ValidationError({campo: 'El archivo está vacío.'})

    extension = os.path.splitext(archivo.name or '')[1].lower()
    permitidas = EXT_IMAGEN | (EXT_PDF if permitir_pdf else set())
    if extension not in permitidas:
        formatos = 'JPG, PNG, WEBP' + (' o PDF' if permitir_pdf else '')
        raise serializers.ValidationError({campo: f'Formato no permitido. Sube una imagen {formatos}.'})

    cabecera = archivo.read(8)
    archivo.seek(0)
    if extension in EXT_PDF:
        if not cabecera.startswith(b'%PDF-'):
            raise serializers.ValidationError({campo: 'El archivo no es un PDF válido.'})
        return archivo

    try:
        with Image.open(archivo) as imagen:
            if imagen.width * imagen.height > MAX_PIXELES:
                raise serializers.ValidationError({campo: 'La imagen es demasiado grande (resolución).'})
            imagen.verify()
    except serializers.ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise serializers.ValidationError({campo: 'El archivo no es una imagen válida.'})
    finally:
        archivo.seek(0)
    return archivo
