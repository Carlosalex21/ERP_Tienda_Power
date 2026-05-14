from rest_framework import viewsets
from django.contrib.auth.models import User
from django.db import transaction
from ..models import UserMetadata
from .serializers_management import UserManagedSerializer
from apps.core.permissions import IsTenantAdmin

class UserManagementViewSet(viewsets.ModelViewSet):
    """
    Permite a los administradores del tenant gestionar a sus empleados
    (invitar, ver, activar/desactivar, asignar rol).
    """
    queryset = UserMetadata.objects.all().select_related('user', 'rol', 'sucursal')
    serializer_class = UserManagedSerializer
    permission_classes = [IsTenantAdmin]

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Crea el objeto User y el UserMetadata asociado.
        """
        validated_data = serializer.validated_data
        user_data = validated_data.pop('user')
        password = validated_data.pop('password', None)

        # Crear el usuario de Django
        new_user = User.objects.create(
            username=user_data['email'], # Usamos email como username
            email=user_data['email'],
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', '')
        )
        if password:
            new_user.set_password(password)
        new_user.save()

        # Crear el UserMetadata y asociarlo
        UserMetadata.objects.create(user=new_user, **validated_data)