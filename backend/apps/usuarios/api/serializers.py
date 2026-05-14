from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from ..models import UserMetadata

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Añadir datos personalizados al token
        token['username'] = user.username
        if hasattr(user, 'metadata') and user.metadata.rol:
            token['rol'] = user.metadata.rol.nombre
        else:
            token['rol'] = None
        return token

class UserMeSerializer(serializers.ModelSerializer):
    """
    Serializer para el endpoint /me, mostrando los datos del usuario actual.
    """
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    rol = serializers.CharField(source='rol.nombre', read_only=True, allow_null=True)
    sucursal = serializers.CharField(source='sucursal.nombre', read_only=True, allow_null=True)

    class Meta:
        model = UserMetadata
        fields = ('id', 'email', 'first_name', 'last_name', 'rol', 'sucursal')