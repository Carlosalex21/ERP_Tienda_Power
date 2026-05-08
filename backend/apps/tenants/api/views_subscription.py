from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from tenants.models import Plan, Subscription, Client
from tenants.services.subscription_service import SubscriptionService

class PlanViewSet(viewsets.ViewSet):
    """
    ViewSet para listar los planes disponibles. (Público)
    """
    permission_classes = [AllowAny]

    def list(self, request):
        planes = Plan.objects.filter(activo=True).values(
            'id', 'nombre', 'descripcion', 'precio', 'limite_usuarios', 'limite_sucursales'
        )
        return Response(planes)

class SubscriptionCUD(APIView):
    """
    APIView para manejar la creación o actualización de una suscripción 
    después de un pago exitoso (simulado por ahora).
    """
    permission_classes = [IsAuthenticated] # Asumimos que el dueño está logueado en el public schema

    def post(self, request):
        client_id = request.data.get('client_id')
        plan_id = request.data.get('plan_id')

        if not client_id or not plan_id:
            return Response({"error": "Faltan datos requeridos (client_id, plan_id)"}, status=status.HTTP_400_BAD_REQUEST)

        # En un escenario real, aquí validaríamos que el pago en la pasarela (ej. PagoMovil o Stripe)
        # fue exitoso antes de llamar a create_subscription.
        
        try:
            sub = SubscriptionService.create_subscription(client_id=client_id, plan_id=plan_id)
            return Response({
                "message": "Suscripción creada/actualizada exitosamente",
                "estado": sub.estado,
                "fecha_fin": sub.fecha_fin
            }, status=status.HTTP_201_CREATED)
        except Client.DoesNotExist:
            return Response({"error": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Plan.DoesNotExist:
            return Response({"error": "Plan no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
