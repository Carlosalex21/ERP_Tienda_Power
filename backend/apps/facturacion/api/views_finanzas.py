# apps/facturacion/api/views_finanzas.py
from rest_framework import viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse

from apps.facturacion.models import MetodoPago, Transaccionpago, Devolucion
from apps.facturacion.api.serializers import MetodoPagoSerializer, TransaccionpagoSerializer, DevolucionSerializer

class MetodoPagoViewSet(viewsets.ModelViewSet):
    queryset = MetodoPago.objects.filter(activo=True).order_by("nombre")
    serializer_class = MetodoPagoSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()

class TransaccionpagoViewSet(viewsets.ModelViewSet):
    queryset = Transaccionpago.objects.filter(activo=True).order_by("-fecha")
    serializer_class = TransaccionpagoSerializer
    permission_classes = [permissions.IsAuthenticated]

class TransaccionpagoByMetodo(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, metodo):
        queryset = Transaccionpago.objects.filter(metodo_pago=metodo).order_by("-fecha")
        serializer = TransaccionpagoSerializer(queryset, many=True)
        return JsonResponse({"transacciones": serializer.data})

class DevolucionViewSet(viewsets.ModelViewSet):
    queryset = Devolucion.objects.filter(activo=True).order_by("-fecha_solicitud")
    serializer_class = DevolucionSerializer
    permission_classes = [permissions.IsAuthenticated]