from django.db.models import Q
from rest_framework import viewsets

from apps.core.permissions import IsTenantAdmin

from ..models import RegistroAuditoria
from .serializers import RegistroAuditoriaSerializer


class RegistroAuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Solo lectura, a propósito -- un registro de auditoría que se puede
    editar o borrar desde la API no sirve para nada (ver `RegistroAuditoria.delete`,
    que además lo bloquea a nivel de modelo como segunda barrera).
    """
    queryset = RegistroAuditoria.objects.select_related('usuario').all()
    serializer_class = RegistroAuditoriaSerializer
    permission_classes = [IsTenantAdmin]
    filterset_fields = ['modelo', 'accion', 'usuario']

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        fecha_desde = params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha__date__gte=fecha_desde)
        fecha_hasta = params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha__date__lte=fecha_hasta)

        q = params.get('q')
        if q:
            qs = qs.filter(
                Q(objeto_repr__icontains=q)
                | Q(usuario_nombre__icontains=q)
                | Q(objeto_id__icontains=q)
            )
        return qs
