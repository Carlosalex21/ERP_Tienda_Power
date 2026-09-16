"""
Roles del tenant.

Antes no existía ningún endpoint funcional para listarlos (había un intento
en ``views_users.py`` que importaba un ``RolSerializer`` que nunca se creó
-- nunca se detectó porque ese archivo tampoco estaba registrado en ninguna
URL). El frontend de RRHH hardcodeaba 3 roles con IDs fijos (1, 2, 3) en vez
de consultar los roles reales de cada tenant.
"""
from rest_framework import viewsets, permissions

from .views_auth import IsAdmin
from .serializers import RolSerializer
from ..models import Rol


class RolViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Solo lectura: los roles se siembran al crear el tenant
    (``TenantService._seed_tenant_defaults``) y no se gestionan desde el panel.

    Sin paginación a propósito: son 5 roles como mucho por tenant, y el
    frontend los consume como un array plano para poblar un <select> (ver
    ``rrhhService.getRoles``) -- la paginación por defecto del proyecto
    envolvería la respuesta en ``{count, next, previous, results}`` y
    rompería ese contrato.
    """
    queryset = Rol.objects.filter(activo=True).order_by('nombre')
    serializer_class = RolSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    pagination_class = None
