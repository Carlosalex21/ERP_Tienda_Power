from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django_tenants.utils import tenant_context

from .services.b2b_service import procesar_carga_masiva_clientes_b2b, BulkUploadError
from .models import InvitacionB2B
from apps.tenants.models import Client

@shared_task(bind=True)
def task_procesar_carga_masiva_clientes(self, file_content: bytes, file_name: str, tenant_id: int, user_id: int):
    """
    Tarea asíncrona de Celery para orquestar la carga masiva de clientes B2B.
    """
    try:
        tenant = Client.objects.get(id=tenant_id)
    except Client.DoesNotExist:
        return f"Error crítico: Tenant con ID {tenant_id} no encontrado."

    with tenant_context(tenant):
        try:
            resultado = procesar_carga_masiva_clientes_b2b(file_content, file_name)
            
            # Dispara una tarea hija por cada correo a enviar
            for invitacion_id in resultado.get("invitaciones_ids_a_enviar", []):
                task_enviar_correo_invitacion_b2b.delay(invitacion_id, tenant.id)

            # Aquí se podría implementar una notificación al usuario (user_id)
            # vía WebSockets o un email de resumen con el `resultado`.
            print(f"Procesamiento completado para tenant {tenant.schema_name}. Resultado: {resultado}")
            return resultado

        except BulkUploadError as e:
            print(f"Error de validación en carga masiva para tenant {tenant.schema_name}: {e}")
            return {"error": str(e), "details": e.errors}
        except Exception as e:
            print(f"Error inesperado en task_procesar_carga_masiva_clientes: {e}")
            # Reintentar la tarea podría ser una opción en producción
            self.retry(exc=e, countdown=60, max_retries=3)


@shared_task(max_retries=3, default_retry_delay=300)
def task_enviar_correo_invitacion_b2b(invitacion_id: int, tenant_id: int):
    """
    Tarea asíncrona para enviar un único correo de invitación a un cliente B2B.
    """
    tenant = Client.objects.get(id=tenant_id)
    
    with tenant_context(tenant):
        try:
            invitacion = InvitacionB2B.objects.select_related('cliente_b2b').get(id=invitacion_id)
            if invitacion.utilizada:
                return f"Invitación {invitacion_id} ya fue utilizada. No se envió correo."

            # Construye la URL de activación. El frontend debe estar en esta ruta.
            domain = tenant.domains.get(is_primary=True)
            base_url = f"http://{domain.domain}:3000" # Puerto 3000 para desarrollo
            activation_url = f"{base_url}/b2b/activar?token={invitacion.token}"

            subject = f"Invitación para unirse al portal de {tenant.nombre_empresa}"
            message = f"""
            Hola {invitacion.cliente_b2b.razon_social},

            Has sido invitado por {tenant.nombre_empresa} para unirte a su portal de clientes B2B.
            Para activar tu cuenta y establecer tu contraseña, por favor haz clic en el siguiente enlace:
            {activation_url}

            Este enlace expirará pronto.

            Saludos,
            El equipo de {tenant.nombre_empresa}
            """
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [invitacion.email])
            return f"Correo de invitación enviado a {invitacion.email}."
        except InvitacionB2B.DoesNotExist:
            return f"Error: No se encontró la invitación con ID {invitacion_id} en el tenant {tenant.schema_name}."
        except Exception as e:
            print(f"Fallo al enviar correo para invitación {invitacion_id}: {e}")
            raise # Reintentar la tarea