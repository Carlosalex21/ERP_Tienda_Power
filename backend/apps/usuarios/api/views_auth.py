from rest_framework.permissions import BasePermission, AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer, UserMeSerializer
from rest_framework.views import APIView
from rest_framework.response import Response

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        metadata = getattr(request.user, 'metadata', None)
        return bool(metadata and metadata.rol and metadata.rol.nombre == 'Administrador')

class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer

class UserMeView(APIView):
    """
    Vista para obtener los datos del usuario actualmente autenticado.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserMeSerializer

    def get(self, request):
        serializer = self.serializer_class(request.user.metadata)
        return Response(serializer.data)