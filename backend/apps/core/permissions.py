from rest_framework.permissions import BasePermission

# Códigos estables de rol (ver Rol.codigo). Comparar contra estos en vez de
# contra `Rol.nombre` evita que renombrar un rol desde el panel rompa la
# autorización en silencio. Para roles sembrados antes de que existiera
# `codigo` (o roles personalizados sin código), se degrada comparando el
# nombre en minúsculas contra el propio código como red de seguridad.
ROL_ADMIN = "admin"
ROL_VENDEDOR = "vendedor"
ROL_CAJERO = "cajero"
ROL_ALMACENISTA = "almacenista"
ROL_RRHH = "rrhh"

_NOMBRE_A_CODIGO_LEGACY = {
    "administrador": ROL_ADMIN,
    "vendedor": ROL_VENDEDOR,
    "cajero": ROL_CAJERO,
    "almacenista": ROL_ALMACENISTA,
    "rrhh": ROL_RRHH,
}


def codigo_rol(rol) -> str:
    """Código estable del rol, con fallback por nombre para roles legado sin `codigo`."""
    if not rol:
        return ""
    if rol.codigo:
        return rol.codigo
    return _NOMBRE_A_CODIGO_LEGACY.get((rol.nombre or "").strip().lower(), "")


class IsTenantAdmin(BasePermission):
    """
    Permite el acceso solo a usuarios cuyo rol tiene código de administrador.
    """
    message = "No tienes permisos de administrador para realizar esta acción."

    def has_permission(self, request, view):
        # Asegurarse de que el usuario esté autenticado y tenga metadatos
        if not request.user or not request.user.is_authenticated or not hasattr(request.user, 'metadata'):
            return False
        return codigo_rol(request.user.metadata.rol) == ROL_ADMIN

class IsAdminOrVendedor(BasePermission):
    """
    Permite el acceso a usuarios cuyo rol es administrador o vendedor.
    """
    message = "No tienes permisos suficientes para realizar esta acción."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not hasattr(request.user, 'metadata'):
            return False

        return codigo_rol(request.user.metadata.rol) in (ROL_ADMIN, ROL_VENDEDOR)

class IsAdminOrAlmacenista(BasePermission):
    """
    Permite el acceso a usuarios cuyo rol es administrador o almacenista --
    los ajustes de inventario (entrada/salida manual de stock) son tarea de
    almacén, no de ventas.
    """
    message = "No tienes permisos suficientes para realizar esta acción."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not hasattr(request.user, 'metadata'):
            return False

        return codigo_rol(request.user.metadata.rol) in (ROL_ADMIN, ROL_ALMACENISTA)