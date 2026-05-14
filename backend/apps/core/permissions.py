from rest_framework.permissions import BasePermission

class IsTenantAdmin(BasePermission):
    """
    Permite el acceso solo a usuarios que tienen el rol de 'Administrador'
    dentro de los metadatos de su perfil.
    """
    message = "No tienes permisos de administrador para realizar esta acción."

    def has_permission(self, request, view):
        # Asegurarse de que el usuario esté autenticado y tenga metadatos
        if not request.user or not request.user.is_authenticated or not hasattr(request.user, 'metadata'):
            return False
        # Comprobar si el rol del usuario es 'Administrador'
        return request.user.metadata.rol and request.user.metadata.rol.nombre == 'Administrador'

class IsAdminOrVendedor(BasePermission):
    """
    Permite el acceso a usuarios que tienen el rol de 'Administrador' o 'Vendedor'.
    """
    message = "No tienes permisos suficientes para realizar esta acción."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not hasattr(request.user, 'metadata'):
            return False
        
        rol_nombre = request.user.metadata.rol.nombre if request.user.metadata.rol else ''
        return rol_nombre in ['Administrador', 'Vendedor']