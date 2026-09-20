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

# El registro real de un pago pasa por `pagos_service.procesar_pago_factura_service`
# (ver `views_pagos.py`/`views_terminal.py`), que valida montos contra el
# saldo de la factura, descuenta stock una sola vez, etc. -- el frontend
# solo LEE de estos dos ViewSets (ver `facturacionService.ts`), nunca
# escribe. Estando como `ModelViewSet` completo con solo `IsAuthenticated`,
# cualquier empleado logueado podía crear una "Transaccionpago" con
# `estado='exitoso'` fabricada (sin pasar dinero real) o inventar
# devoluciones, sin ninguna validación de monto. Se dejan de solo lectura;
# un futuro flujo de reembolsos debe tener su propio service validado, no
# reabrir este CRUD crudo.
class TransaccionpagoViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = Transaccionpago.objects.select_related('metodo_pago', 'factura').filter(activo=True).order_by("-fecha")
    serializer_class = TransaccionpagoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['factura', 'estado']

class TransaccionpagoByMetodo(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, metodo):
        queryset = Transaccionpago.objects.filter(metodo_pago=metodo).order_by("-fecha")
        serializer = TransaccionpagoSerializer(queryset, many=True)
        return JsonResponse({"transacciones": serializer.data})

class DevolucionViewSet(viewsets.ModelViewSet):
    http_method_names = ['get', 'head', 'options']
    queryset = Devolucion.objects.filter(activo=True).order_by("-fecha_solicitud")
    serializer_class = DevolucionSerializer
    permission_classes = [permissions.IsAuthenticated]