from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from apps.inventario.services.catalog_service import obtener_inventario_unificado, obtener_categorias_activas

class PublicCatalogView(APIView):
    """
    Expone el catálogo de productos y variantes a clientes no autenticados (Catálogo del SaaS).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            categoria_id = request.query_params.get('categoria_id')
            inventario = obtener_inventario_unificado(categoria_id=categoria_id)
            categorias = obtener_categorias_activas()
            
            return Response({
                "categorias": categorias,
                "productos": inventario
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
