from django.urls import path
from .api.views_subscription import PlanViewSet, SubscriptionCUD

urlpatterns = [
    # Endpoint para listar los planes disponibles (público)
    path('plans/', PlanViewSet.as_view({'get': 'list'}), name='plan-list'),

    # Endpoint para crear/actualizar una suscripción (requiere autenticación del dueño del tenant)
    path('subscriptions/', SubscriptionCUD.as_view(), name='subscription-cud'),
]