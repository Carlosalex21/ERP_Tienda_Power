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
        from apps.core.plan_limits import verificar_limite

        verificar_limite(
            self.request, 'limite_usuarios',
            User.objects.filter(is_active=True).count(), 'usuarios',
        )

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

        # Crear el UserMetadata y asociarlo. Hay que asignar `serializer.instance`
        # a mano -- `ModelViewSet.create()` (DRF) llama a `serializer.data`
        # DESPUÉS de este método para armar la respuesta, y sin `instance`
        # cae a representar `validated_data` como si fuera el objeto (un
        # dict plano). Como arriba ya se hizo `validated_data.pop('user')`,
        # ese dict ya no tiene la clave `user` que el campo `email` (entre
        # otros, `source='user.email'`) necesita para leerse -- reventaba
        # con `KeyError: 'user'` en CADA invitación exitosa (el usuario SÍ
        # quedaba creado, pero la respuesta nunca llegaba a devolverse).
        serializer.instance = UserMetadata.objects.create(user=new_user, **validated_data)

    @transaction.atomic
    def perform_update(self, serializer):
        """
        Actualiza el `User` (email/nombre/is_active) y el `UserMetadata`
        (rol/sucursal) asociados. Sin este override, el `update()` genérico
        de DRF intentaría hacer `setattr(instance, 'user', {...})` con el
        dict anidado que el serializer produce para los campos con
        `source='user.*'` -- eso no existe en `ModelSerializer` (los campos
        anidados por punto solo funcionan solos al leer, no al escribir) y
        rompía cualquier edición.
        """
        instance = serializer.instance
        validated_data = serializer.validated_data
        user_data = validated_data.pop('user', {})
        # La contraseña es opcional al editar -- solo se resetea si el admin
        # escribió una nueva; dejarla en blanco no debe borrar la existente.
        password = validated_data.pop('password', None)

        user = instance.user
        for attr, value in user_data.items():
            setattr(user, attr, value)
        if user_data.get('email'):
            # `username` se sembró igual al email al crear el usuario; se
            # mantiene sincronizado si el admin le cambia el correo.
            user.username = user_data['email']
        if password:
            user.set_password(password)
        user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()