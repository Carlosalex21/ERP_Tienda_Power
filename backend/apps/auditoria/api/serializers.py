from rest_framework import serializers

from ..models import RegistroAuditoria


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroAuditoria
        fields = [
            'id', 'fecha', 'usuario', 'usuario_nombre', 'accion',
            'modelo', 'objeto_id', 'objeto_repr', 'cambios', 'ip_address',
        ]
        read_only_fields = fields
