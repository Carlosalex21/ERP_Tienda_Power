from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.usuarios.models import Rol, Sesionusuario, Logactividad, UserMetadata
from apps.inventario.models import Almacen

User = get_user_model()

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user_metadata = getattr(self.user, 'metadata', None)
        if user_metadata and user_metadata.rol:
            data['role'] = user_metadata.rol.nombre
            data['nombre_usuario'] = user_metadata.user.get_full_name() or user_metadata.user.username
        return data

class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ['id', 'nombre', 'descripcion', 'activo']

class UserSerializerForMetadata(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_active']

class UserMetadataSerializer(serializers.ModelSerializer):
    user = UserSerializerForMetadata(read_only=True)
    rol = RolSerializer(read_only=True)
    
    class Meta:
        model = UserMetadata
        fields = '__all__'

class UserMetadataCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    rol = serializers.PrimaryKeyRelatedField(queryset=Rol.objects.all(), required=False)

    class Meta:
        model = UserMetadata
        fields = ['username', 'password', 'email', 'rol', 'telefono', 'direccion', 'puesto']

class LogactividadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Logactividad
        fields = '__all__'

class SesionusuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sesionusuario
        fields = '__all__'