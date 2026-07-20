from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import serializers
from django.contrib.auth.models import User

class PublicUserSerializer(serializers.ModelSerializer):
    """
    Serializer simple para el usuario del esquema público (administrador de la plataforma).
    No depende de UserMetadata.
    """
    rol = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'rol')

    def get_rol(self, obj):
        """
        Asigna un rol estático para los administradores de la plataforma.
        """
        if obj.is_superuser:
            return "Platform SuperAdmin"
        return "Platform Admin"

class PublicUserMeView(APIView):
    """
    Vista para obtener los datos del usuario PÚBLICO (administrador) actualmente autenticado.
    """
    permission_classes = [IsAuthenticated, IsAdminUser] # Asegura que solo admins puedan usarlo
    serializer_class = PublicUserSerializer

    def get(self, request):
        serializer = PublicUserSerializer(request.user)
        return Response(serializer.data)