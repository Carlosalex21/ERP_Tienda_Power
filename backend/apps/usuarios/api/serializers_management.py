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
    # `id` (arriba) es el pk de `UserMetadata`, NO el del `User` -- son
    # secuencias independientes que solo coinciden por casualidad. Nómina,
    # vacaciones y liquidación referencian al empleado por `User.pk` (ver
    # `NominaEmpleado.usuario`), así que el frontend necesita este campo
    # aparte para esas llamadas en vez de asumir que `id` sirve para eso.
    usuario_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = UserMetadata
        fields = (
            'id', 'usuario_id', 'email', 'first_name', 'last_name', 'is_active', 'rol', 'sucursal',
            'departamento', 'sueldo_base', 'fecha_contratacion', 'password',
        )
        read_only_fields = ('id',)