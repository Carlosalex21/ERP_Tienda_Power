from rest_framework.permissions import BasePermission

from apps.core.permissions import IsTenantAdmin, ROL_ADMIN, ROL_CAJERO, ROL_VENDEDOR, codigo_rol


class EsPersonal(BasePermission):
    """Administrador, vendedor (asesor/cobranza) o cajero: pueden operar el día a día."""
    message = 'No tienes permisos para esta acción.'

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario or not usuario.is_authenticated or not hasattr(usuario, 'metadata'):
            return False
        return codigo_rol(usuario.metadata.rol) in (ROL_ADMIN, ROL_VENDEDOR, ROL_CAJERO)


class PermisosPorAccion:
    """Mixin: `acciones_admin` solo para el administrador; el resto, para el personal."""
    acciones_admin: tuple[str, ...] = ('destroy',)

    def get_permissions(self):
        clase = IsTenantAdmin if getattr(self, 'action', None) in self.acciones_admin else EsPersonal
        return [clase()]
