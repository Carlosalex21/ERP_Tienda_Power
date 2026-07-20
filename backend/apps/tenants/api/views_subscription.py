from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from apps.tenants.models import Plan, Subscription, Client, Domain
from apps.tenants.services.subscription_service import SubscriptionService
from apps.tenants.services.tenant_service import TenantService, TenantCreationError
from .serializers import PlanSerializer, SubscriptionCreateSerializer, SubscriptionResponseSerializer, PlatformClientSerializer, TenantRegistrationSerializer, TenantProfileSerializer

class PlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar los Planes de Suscripción.
    - `list`: Público, cualquiera puede ver los planes activos.
    - `retrieve`, `create`, `update`, `destroy`: Solo para administradores de la plataforma.
    """
    queryset = Plan.objects.all().order_by('precio')
    serializer_class = PlanSerializer

    def get_permissions(self):
        """
        Asigna permisos basados en la acción.
        """
        if self.action == 'list':
            # Cualquiera puede listar los planes
            self.permission_classes = [AllowAny]
        else:
            # Solo los administradores de la plataforma pueden crear, editar o eliminar planes.
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()

    def get_queryset(self):
        """
        Para la acción 'list', solo muestra los planes activos.
        Para otras acciones (admin), muestra todos.
        """
        if self.action == 'list':
            return self.queryset.filter(activo=True)
        return self.queryset

class PlatformClientViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para que el administrador de la plataforma vea la lista de inquilinos (Clients).
    Es de solo lectura, ya que la modificación de un inquilino (cambio de plan, etc.)
    debe ser un proceso automatizado y no manual.
    """
    queryset = Client.objects.all().select_related(
        'owner', 
        'subscription__plan'
    ).prefetch_related(
        'domains'
    ).order_by('-fecha_creacion')
    
    serializer_class = PlatformClientSerializer
    permission_classes = [IsAdminUser]

class TenantRegistrationView(APIView):
    """
    Endpoint público para el registro de un nuevo cliente (tenant).
    Crea el usuario dueño, el tenant, el dominio y la suscripción inicial.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Registrar Nuevo Cliente y Tenant",
        request=TenantRegistrationSerializer,
        responses={
            201: {"description": "Registro exitoso. Se ha creado el tenant y el usuario."},
            400: {"description": "Datos inválidos o el subdominio/email ya existe."},
        }
    )
    def post(self, request):
        serializer = TenantRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            TenantService.create_tenant(
                username=data['username'], email=data['email'], 
                password=data['password'], first_name=data['first_name'], 
                last_name=data['last_name'], nombre_empresa=data['nombre_empresa'], tipo_negocio=data['tipo_negocio'],
                subdomain=data['subdomain'],
                plan_id=data.get('plan_id')
            )
        except TenantCreationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error inesperado en registro de tenant: {e}") # Log para debug
            return Response({"error": "Ocurrió un error inesperado durante el registro."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Para el mensaje de respuesta, mostramos el dominio sin el puerto para consistencia.
        base_domain_with_port = getattr(settings, 'TENANT_DOMAIN', 'localhost')
        base_domain = base_domain_with_port.split(':')[0]
        return Response({"message": f"¡Registro exitoso! Tu espacio de trabajo está listo en {data['subdomain']}.{base_domain}"}, status=status.HTTP_201_CREATED)

class SubdomainAvailabilityView(APIView):
    """
    Verifica si un subdominio está disponible para ser registrado.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verificar Disponibilidad de Subdominio",
        parameters=[
            OpenApiParameter(name='subdomain', description='El subdominio a verificar (ej: mi-tienda).', required=True, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {"description": "Respuesta sobre la disponibilidad."},
            400: {"description": "Falta el parámetro 'subdomain'."}
        }
    )
    def get(self, request):
        subdomain = request.query_params.get('subdomain', '').lower().strip()
        if not subdomain:
            return Response({"error": "El parámetro 'subdomain' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Verificar palabras reservadas
        reserved_subdomains = ['www', 'api', 'admin', 'mail', 'app', 'public', 'static']
        if subdomain in reserved_subdomains:
            return Response({"available": False, "message": "Este subdominio está reservado."}, status=status.HTTP_200_OK)
        
        # 2. Verificar si ya existe en la base de datos
        # Nos aseguramos de que el dominio base no incluya el puerto para la comparación.
        base_domain_with_port = getattr(settings, 'TENANT_DOMAIN', 'localhost')
        base_domain = base_domain_with_port.split(':')[0]
        full_domain = f"{subdomain}.{base_domain}"
        
        if Domain.objects.filter(domain=full_domain).exists():
            return Response({"available": False, "message": "Este subdominio ya está en uso."}, status=status.HTTP_200_OK)
            
        return Response({"available": True}, status=status.HTTP_200_OK)

class SubscriptionCUD(APIView):
    """
    APIView para manejar la creación o actualización de una suscripción 
    después de un pago exitoso (simulado por ahora).
    """
    permission_classes = [IsAuthenticated] # Asumimos que el dueño está logueado en el public schema

    @extend_schema(
        summary="Crear o Actualizar una Suscripción",
        description="Este endpoint se llama después de que un pago es confirmado por la pasarela. Crea o renueva la suscripción de un cliente a un plan.",
        request=SubscriptionCreateSerializer,
        responses={
            201: SubscriptionResponseSerializer,
            400: {"description": "Datos de entrada inválidos"},
            404: {"description": "Cliente o Plan no encontrado"},
        }
    )
    def post(self, request):
        client_id = request.data.get('client_id')
        plan_id = request.data.get('plan_id')

        if not client_id or not plan_id:
            return Response({"error": "Faltan datos requeridos (client_id, plan_id)"}, status=status.HTTP_400_BAD_REQUEST)

        # --- MEJORA DE SEGURIDAD CRÍTICA ---
        # Verificar que el usuario que hace la petición es el dueño del tenant.
        client = get_object_or_404(Client, id=client_id)
        if client.owner != request.user:
            return Response({"error": "No tienes permiso para modificar esta suscripción."}, status=status.HTTP_403_FORBIDDEN)

        # En un escenario real, aquí validaríamos que el pago en la pasarela (ej. PagoMovil o Stripe)
        # fue exitoso antes de llamar a create_subscription.
        
        try:
            sub = SubscriptionService.create_subscription(client_id=client_id, plan_id=plan_id)
            serializer = SubscriptionResponseSerializer(sub)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Client.DoesNotExist:
            return Response({"error": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Plan.DoesNotExist:
            return Response({"error": "Plan no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TenantProfileView(generics.RetrieveAPIView):
    """
    Devuelve el perfil del tenant actual basado en el subdominio de la petición.
    Esencial para que el frontend conozca el contexto (ej: tipo_negocio).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TenantProfileSerializer

    def get_object(self):
        """
        Devuelve el objeto tenant asociado a la petición actual.
        """
        return self.request.tenant
