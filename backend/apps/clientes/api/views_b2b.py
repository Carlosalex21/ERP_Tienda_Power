from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404

from .serializers_b2b import ClienteB2BBulkUploadSerializer, B2BAccountActivationSerializer, ClienteB2BProfileSerializer
from ..tasks import task_procesar_carga_masiva_clientes
from ..models import InvitacionB2B, ClienteB2B


# --- VISTAS DE ONBOARDING Y GESTIÓN ---
class ClienteB2BBulkUploadView(APIView):
    """
    Endpoint para la carga masiva de Clientes B2B desde un archivo CSV o Excel.

    El archivo debe contener las siguientes columnas:
    - `razon_social`: Nombre legal de la empresa cliente.
    - `rif`: Identificador fiscal único.
    - `email_contacto`: Correo para la invitación y comunicación.
    - `nivel_precio`: El nombre exacto de un Nivel de Precio ya existente en el sistema.
    """
    permission_classes = [permissions.IsAdminUser] # Solo administradores del tenant
    serializer_class = ClienteB2BBulkUploadSerializer

    @extend_schema(
        summary="Carga Masiva de Clientes B2B",
        request=ClienteB2BBulkUploadSerializer,
        responses={
            202: {"description": "Procesamiento iniciado. Se enviará un resumen por correo."},
            400: {"description": "Archivo inválido o error en los datos."},
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']
        tenant = request.tenant
        user = request.user
        
        # Delegamos el procesamiento pesado a una tarea asíncrona de Celery
        task_procesar_carga_masiva_clientes.delay(
            file_content=uploaded_file.read(),
            file_name=uploaded_file.name,
            tenant_id=tenant.id,
            user_id=user.id
        )
        return Response(
            {"message": "Archivo recibido. El procesamiento ha comenzado en segundo plano. Recibirás una notificación cuando termine."},
            status=status.HTTP_202_ACCEPTED
        )


# --- VISTAS DE AUTENTICACIÓN Y ACCESO DEL CLIENTE B2B ---

class B2BAccountActivationView(APIView):
    """
    Permite a un cliente B2B activar su cuenta usando el token de invitación.
    """
    permission_classes = [permissions.AllowAny] # Es un endpoint público
    serializer_class = B2BAccountActivationSerializer

    @extend_schema(
        summary="Activar Cuenta de Cliente B2B",
        request=B2BAccountActivationSerializer,
        responses={
            200: {"description": "Cuenta activada exitosamente."},
            400: {"description": "Datos inválidos (ej: token expirado, contraseñas no coinciden)."},
            404: {"description": "Token no encontrado."},
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['token']
        password = serializer.validated_data['password']

        try:
            # Usamos select_related para optimizar la consulta a la BD
            invitacion = InvitacionB2B.objects.select_related('cliente_b2b').get(token=token)
        except InvitacionB2B.DoesNotExist:
            return Response({"error": "El token de invitación es inválido o no existe."}, status=status.HTTP_404_NOT_FOUND)

        if invitacion.utilizada:
            return Response({"error": "Esta invitación ya ha sido utilizada."}, status=status.HTTP_400_BAD_REQUEST)

        if invitacion.is_expired():
            return Response({"error": "Esta invitación ha expirado. Contacta al proveedor para una nueva."}, status=status.HTTP_400_BAD_REQUEST)

        cliente_b2b = invitacion.cliente_b2b
        TenantUser = get_user_model()

        if TenantUser.objects.filter(email__iexact=cliente_b2b.email_contacto).exists():
            return Response({"error": "Ya existe un usuario registrado con este correo electrónico."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Creamos el usuario dentro del tenant
            new_user = TenantUser.objects.create_user(
                username=cliente_b2b.email_contacto,
                email=cliente_b2b.email_contacto,
                password=password
            )
            cliente_b2b.user = new_user
            cliente_b2b.estado = 'activo'
            invitacion.utilizada = True
            cliente_b2b.save()
            invitacion.save()

        return Response({"message": "¡Tu cuenta ha sido activada exitosamente! Ya puedes iniciar sesión."}, status=status.HTTP_200_OK)

class ClienteB2BProfileView(generics.RetrieveAPIView):
    """
    Endpoint para que un cliente B2B autenticado vea su perfil.
    Devuelve información clave como su nivel de precio y límite de crédito.
    """
    serializer_class = ClienteB2BProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
        Devuelve el objeto ClienteB2B asociado al usuario autenticado.
        """
        try:
            # El usuario autenticado (request.user) tiene una relación uno a uno
            # con el perfil ClienteB2B a través del related_name 'cliente_b2b'.
            return self.request.user.cliente_b2b
        except ClienteB2B.DoesNotExist:
            # Esto no debería ocurrir si el usuario B2B está correctamente configurado.
            raise Http404