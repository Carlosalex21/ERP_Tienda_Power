from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from apps.tenants.models import Plan, Subscription, Client
from apps.tenants.services.subscription_service import SubscriptionService
from .serializers import PlanSerializer, SubscriptionCreateSerializer, SubscriptionResponseSerializer

class PlanViewSet(viewsets.ViewSet):
    """
    ViewSet para listar los planes disponibles. (Público)
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Listar Planes de Suscripción",
        responses=PlanSerializer(many=True)
    )
    def list(self, request):
        queryset = Plan.objects.filter(activo=True)
        serializer = PlanSerializer(queryset, many=True)
        return Response(serializer.data)

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
