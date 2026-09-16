from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor, ROL_ADMIN, ROL_VENDEDOR, codigo_rol

from ..models import UserMetadata


class VendedoresListView(APIView):
    """
    Lista liviana de empleados que pueden figurar como vendedor de una
    venta (admins y vendedores) -- usada por el selector "Vendedor" del POS.

    A propósito NO reutiliza `UserManagementViewSet` (exige admin): un
    vendedor logueado en el POS necesita poder ver esta lista para
    atribuirle la venta a un compañero que la cerró en la calle, no solo
    el admin.
    """
    permission_classes = [IsAdminOrVendedor]

    def get(self, request):
        metadatas = (
            UserMetadata.objects.select_related('user', 'rol')
            .filter(user__is_active=True)
        )
        data = [
            {
                'id': m.user_id,
                'nombre': m.user.get_full_name() or m.user.username,
                'rol': codigo_rol(m.rol),
            }
            for m in metadatas
            if codigo_rol(m.rol) in (ROL_ADMIN, ROL_VENDEDOR)
        ]
        return Response(data)
