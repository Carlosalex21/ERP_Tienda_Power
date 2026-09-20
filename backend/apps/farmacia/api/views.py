from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets

from apps.core.permissions import IsAdminOrAlmacenista

from ..models import LoteProducto
from .serializers import LoteProductoSerializer


class LoteProductoViewSet(viewsets.ModelViewSet):
    queryset = LoteProducto.objects.select_related('producto').filter(activo=True)
    serializer_class = LoteProductoSerializer
    permission_classes = [IsAdminOrAlmacenista]

    def get_queryset(self):
        qs = super().get_queryset()
        producto_id = self.request.query_params.get('producto')
        if producto_id:
            qs = qs.filter(producto_id=producto_id)
        # `?dias=30` -- solo lotes que vencen dentro de esa ventana (incluye
        # los ya vencidos, para no perderlos de vista). Sin este filtro se
        # listan todos, para la pantalla de gestión de lotes.
        dias = self.request.query_params.get('dias')
        if dias is not None:
            limite = timezone.now().date() + timedelta(days=int(dias))
            qs = qs.filter(fecha_vencimiento__lte=limite)
        return qs.order_by('fecha_vencimiento')

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save(update_fields=['activo'])
