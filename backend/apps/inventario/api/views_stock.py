# apps/inventario/api/views_stock.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# Importamos nuestros servicios
from apps.inventario.core.catalog_service import obtener_inventario_unificado, obtener_categorias_activas

class InventarioActualView(APIView):
    """
    Devuelve el catálogo unificado para la pantalla de inventario o POS.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categoria_id = request.query_params.get('categoria_id')

        try:
            # Llamamos al core lógico
            inventario = obtener_inventario_unificado(categoria_id=categoria_id)
            categorias = obtener_categorias_activas()

            return Response({
                "inventario": inventario,
                "categorias": categorias
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": f"Error al generar el catálogo: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )