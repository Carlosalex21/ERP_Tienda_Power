from celery import shared_task
from django_tenants.utils import tenant_context

from apps.tenants.models import Client
from .services.product_service import procesar_carga_masiva_productos, ProductBulkUploadError

@shared_task(bind=True)
def task_procesar_carga_masiva_productos(self, file_content: bytes, file_name: str, tenant_id: int, user_id: int):
    """
    Tarea asíncrona de Celery para orquestar la carga masiva de productos.
    """
    try:
        tenant = Client.objects.get(id=tenant_id)
    except Client.DoesNotExist:
        # No se puede continuar sin el tenant, es un error crítico.
        return f"Error crítico: Tenant con ID {tenant_id} no encontrado."

    with tenant_context(tenant):
        try:
            resultado = procesar_carga_masiva_productos(file_content, file_name)
            
            # En un futuro, aquí se podría implementar una notificación al usuario (user_id)
            # vía WebSockets o un email de resumen con el `resultado`.
            print(f"Procesamiento de productos completado para tenant {tenant.schema_name}. Resultado: {resultado}")
            return resultado

        except ProductBulkUploadError as e:
            print(f"Error de validación en carga masiva de productos para tenant {tenant.schema_name}: {e}")
            # Notificar al usuario sobre el error de validación.
            return {"error": str(e), "details": e.errors}
        except Exception as e:
            print(f"Error inesperado en task_procesar_carga_masiva_productos: {e}")
            # Reintentar la tarea podría ser una opción en producción para errores transitorios.
            self.retry(exc=e, countdown=60, max_retries=3)