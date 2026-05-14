from rest_framework import serializers
from django.contrib.auth.models import User
from ..models import UserMetadata

class UserManagedSerializer(serializers.ModelSerializer):
    """
    Serializer para que un admin de tenant vea y gestione a sus usuarios.
    """
    email = serializers.CharField(source='user.email')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    is_active = serializers.BooleanField(source='user.is_active')
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})

    class Meta:
        model = UserMetadata
        fields = ('id', 'email', 'first_name', 'last_name', 'is_active', 'rol', 'sucursal', 'password')
        read_only_fields = ('id',)