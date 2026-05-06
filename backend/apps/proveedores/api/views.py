# apps/proveedores/api/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response

from apps.proveedores.models import Proveedor
from apps.proveedores.api.serializers import ProveedorSerializer
from apps.proveedores.core.proveedores_service import desactivar_proveedor_service

class ProveedorViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de proveedores delegando operaciones críticas al Core.
    """
    queryset = Proveedor.objects.filter(activo=True).order_by('id')
    serializer_class = ProveedorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        """
        Sobreescribimos el método DELETE de la API para usar nuestro servicio.
        """
        proveedor = self.get_object()
        try:
            # Delegamos la regla de negocio al CORE
            desactivar_proveedor_service(proveedor.id)
            return Response(
                {"estado": "eliminado", "mensaje": "Proveedor inactivo"},
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            # Capturamos si el servicio rechaza la acción
            return Response(
                {"estado": "error", "mensaje": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )