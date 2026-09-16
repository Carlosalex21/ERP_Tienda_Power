from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics, viewsets
from drf_spectacular.utils import extend_schema
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404

from rest_framework.pagination import PageNumberPagination

from .serializers_b2b import (
    ClienteB2BBulkUploadSerializer,
    B2BAccountActivationSerializer,
    ClienteB2BProfileSerializer,
    B2BProductoSerializer,
    B2BCreateOrderSerializer,
    SugerenciaReposicionSerializer,
    NivelPrecioAdminSerializer,
    ClienteB2BAdminSerializer,
)
from apps.core.tasks import dispatch_task
from ..tasks import task_procesar_carga_masiva_clientes
from ..models import InvitacionB2B, ClienteB2B, NivelPrecio
from ..services.b2b_order_service import crear_pedido_b2b, B2BOrderCreationError
from ..services.reposicion_service import calcular_sugerencias_reposicion
from apps.inventario.models import Producto


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
        
        # Delegamos el procesamiento pesado a una tarea asíncrona de Celery.
        # A diferencia de una notificación (best-effort), aquí SÍ importa que
        # se haya podido encolar: si el broker está caído, nada va a
        # procesar el archivo aunque le digamos 202 al usuario -- mejor
        # avisarle ahora que dejarlo esperando una carga que nunca corre.
        encolada = dispatch_task(
            task_procesar_carga_masiva_clientes,
            file_content=uploaded_file.read(),
            file_name=uploaded_file.name,
            tenant_id=tenant.id,
            user_id=user.id,
        )
        if not encolada:
            return Response(
                {"error": "El servicio de procesamiento en segundo plano no está disponible en este momento. Intenta de nuevo más tarde."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
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


class B2BCatalogoPagination(PageNumberPagination):
    page_size = 20


class B2BCatalogoView(generics.GenericAPIView):
    """
    Catálogo de productos para un cliente B2B autenticado, con el precio ya
    ajustado según su ``NivelPrecio`` (ver ``pricing_service``).

    Antes de esta vista, `NivelPrecio.porcentaje_descuento` se guardaba al
    dar de alta un cliente B2B pero ningún endpoint lo aplicaba realmente.
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = B2BCatalogoPagination
    serializer_class = B2BProductoSerializer

    def get_queryset(self):
        return (
            Producto.objects.filter(activo=True, disponible_online=True)
            .prefetch_related('variacionproducto_set')
            .order_by('nombre')
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['cliente_b2b'] = getattr(self.request.user, 'cliente_b2b', None)
        return context

    @extend_schema(summary="Ver Catálogo B2B con Precios por Nivel", responses=B2BProductoSerializer(many=True))
    def get(self, request):
        try:
            request.user.cliente_b2b
        except ClienteB2B.DoesNotExist:
            return Response(
                {"error": "Esta cuenta no tiene un perfil de cliente B2B asociado."},
                status=status.HTTP_403_FORBIDDEN,
            )

        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class B2BCrearPedidoView(APIView):
    """
    Permite a un cliente B2B autenticado crear un pedido, con cada línea
    cobrada al precio efectivo de su ``NivelPrecio`` (ver ``b2b_order_service``).
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="Crear un Pedido B2B", request=B2BCreateOrderSerializer)
    def post(self, request):
        try:
            cliente_b2b = request.user.cliente_b2b
        except ClienteB2B.DoesNotExist:
            return Response(
                {"error": "Esta cuenta no tiene un perfil de cliente B2B asociado."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = B2BCreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            factura = crear_pedido_b2b(cliente_b2b, serializer.validated_data['items'])
        except B2BOrderCreationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Pedido registrado correctamente.",
                "correlativo": factura.correlativo,
                "total": str(factura.total),
            },
            status=status.HTTP_201_CREATED,
        )


class B2BSugerenciasReposicionView(APIView):
    """
    Ver ``apps.clientes.services.reposicion_service``: para cada producto
    que el cliente B2B ya compró varias veces, proyecta cuándo le tocaría
    volver a pedirlo según su propio ritmo histórico.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="Sugerencias de Reposición B2B", responses=SugerenciaReposicionSerializer(many=True))
    def get(self, request):
        try:
            cliente_b2b = request.user.cliente_b2b
        except ClienteB2B.DoesNotExist:
            return Response(
                {"error": "Esta cuenta no tiene un perfil de cliente B2B asociado."},
                status=status.HTTP_403_FORBIDDEN,
            )

        sugerencias = calcular_sugerencias_reposicion(cliente_b2b)
        return Response(SugerenciaReposicionSerializer(sugerencias, many=True).data)


# --- VISTAS DE ADMINISTRACIÓN (tenant admin) ---

class NivelPrecioAdminViewSet(viewsets.ModelViewSet):
    """CRUD de niveles de precio B2B (nombre, % descuento, umbral de compra)."""
    queryset = NivelPrecio.objects.all().order_by('monto_minimo_periodo')
    serializer_class = NivelPrecioAdminSerializer
    permission_classes = [permissions.IsAdminUser]


class ClienteB2BAdminViewSet(viewsets.ModelViewSet):
    """
    Gestión de clientes B2B para el admin del tenant: ver/editar nivel de
    precio, línea de crédito y estado. La creación real de clientes sigue
    siendo por carga masiva (``ClienteB2BBulkUploadView``); este endpoint
    también permite crear uno suelto si hace falta.
    """
    queryset = ClienteB2B.objects.select_related('nivel_precio').all().order_by('razon_social')
    serializer_class = ClienteB2BAdminSerializer
    permission_classes = [permissions.IsAdminUser]