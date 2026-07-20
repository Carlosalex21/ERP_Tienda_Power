import pandas as pd
import io
from django.db import transaction
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError

from ..models import ClienteB2B, NivelPrecio, InvitacionB2B

class BulkUploadError(Exception):
    """Excepción personalizada para errores durante la carga masiva."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or []

def procesar_carga_masiva_clientes_b2b(file_content: bytes, file_name: str):
    """
    Procesa un archivo (CSV o Excel) para la creación masiva de Clientes B2B.

    Esta función se ejecuta dentro del contexto de un tenant.

    Args:
        file_content (bytes): El contenido del archivo en bytes.
        file_name (str): El nombre original del archivo para determinar el formato.

    Returns:
        dict: Un diccionario con el resumen del proceso (creados, errores, etc.).
    """
    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif file_name.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise BulkUploadError("Formato de archivo no soportado.")
    except Exception as e:
        raise BulkUploadError(f"Error al leer el archivo: {e}")

    # Normalizar nombres de columnas para flexibilidad
    df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]

    required_columns = {'razon_social', 'rif', 'email_contacto', 'nivel_precio'}
    if not required_columns.issubset(df.columns):
        missing = required_columns - set(df.columns)
        raise BulkUploadError(f"Faltan las siguientes columnas obligatorias: {', '.join(missing)}")

    # Pre-cargamos datos para optimizar y evitar consultas en el bucle
    niveles_precio = {nivel.nombre.lower(): nivel for nivel in NivelPrecio.objects.all()}
    existing_rifs = set(ClienteB2B.objects.values_list('rif', flat=True))
    existing_emails = set(ClienteB2B.objects.values_list('email_contacto', flat=True))

    invitaciones_creadas_ids = []
    errores_detalle = []

    for index, row in df.iterrows():
        razon_social = row.get('razon_social')
        rif = str(row.get('rif', '')).strip()
        email = str(row.get('email_contacto', '')).strip().lower()
        nivel_precio_nombre = str(row.get('nivel_precio', '')).strip().lower()

        # --- Validación de datos por fila ---
        if not all([razon_social, rif, email, nivel_precio_nombre]):
            errores_detalle.append({"fila": index + 2, "error": "Faltan datos obligatorios (razon_social, rif, email_contacto, nivel_precio)."})
            continue
        
        if rif in existing_rifs or ClienteB2B.objects.filter(rif=rif).exists():
            errores_detalle.append({"fila": index + 2, "rif": rif, "error": "El RIF ya existe en el sistema."})
            continue

        if email in existing_emails or ClienteB2B.objects.filter(email_contacto=email).exists():
            errores_detalle.append({"fila": index + 2, "email": email, "error": "El email ya existe en el sistema."})
            continue
        
        nivel_precio_obj = niveles_precio.get(nivel_precio_nombre)
        if not nivel_precio_obj:
            errores_detalle.append({"fila": index + 2, "nivel_precio": row.get('nivel_precio'), "error": "El Nivel de Precio especificado no existe."})
            continue

        # --- Creación Atómica de Cliente e Invitación ---
        try:
            with transaction.atomic():
                cliente = ClienteB2B.objects.create(
                    razon_social=razon_social,
                    rif=rif,
                    email_contacto=email,
                    nivel_precio=nivel_precio_obj,
                    telefono_contacto=row.get('telefono_contacto', ''),
                    direccion_fiscal=row.get('direccion_fiscal', ''),
                    limite_credito=pd.to_numeric(row.get('limite_credito'), errors='coerce') or 0.00
                )
                # La invitación se crea explícitamente aquí para tener el ID
                invitacion = InvitacionB2B.objects.create(cliente_b2b=cliente, email=cliente.email_contacto)
                invitaciones_creadas_ids.append(invitacion.id)

        except (IntegrityError, DjangoValidationError) as e:
            errores_detalle.append({"fila": index + 2, "rif": rif, "error": f"Error de base de datos: {e}"})

    return {
        "total_filas": len(df),
        "clientes_creados": len(invitaciones_creadas_ids),
        "errores": errores_detalle,
        "invitaciones_ids_a_enviar": invitaciones_creadas_ids
    }