"""
Historial de inicios de sesión, solo lectura para el admin del tenant.

Los intentos ya se registran desde hace tiempo (`login_attempt_service`, para
el bloqueo por fuerza bruta) pero nunca se mostraban en ningún lado -- el
admin no tenía forma de notar, por ejemplo, una racha de intentos fallidos
desde una IP desconocida contra la cuenta de un empleado.
"""
from __future__ import annotations

from rest_framework import permissions, serializers, viewsets

from .views_auth import IsAdmin
from ..models import LoginAttempt


class LoginAttemptSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = LoginAttempt
        fields = ('id', 'usuario_nombre', 'ip', 'success', 'timestamp')

    def get_usuario_nombre(self, obj: LoginAttempt) -> str:
        return obj.user.get_full_name() or obj.user.username


class LoginAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    http_method_names = ['get', 'head', 'options']
    serializer_class = LoginAttemptSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    # Sin paginación a propósito: el frontend lo consume como un array plano
    # de los últimos 200 intentos (ver `get_queryset`), sin necesidad de
    # controles de paginación para una tabla de este tamaño.
    pagination_class = None

    def get_queryset(self):
        return LoginAttempt.objects.select_related('user').order_by('-timestamp')[:200]
