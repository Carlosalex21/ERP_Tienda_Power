from rest_framework import generics, permissions
from apps.clientes.models import Cliente
from .serializers import ClienteSerializer

class ClienteListCreateView(generics.ListCreateAPIView):
    """
    Vista para listar todos los clientes o crear un nuevo cliente.
    """
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]

class ClienteRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    Vista para ver, actualizar o eliminar un cliente específico por su ID.
    """
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]