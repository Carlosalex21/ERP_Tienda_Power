from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .views_auth import IsAdmin
from ..services.usuarios_service import crear_empleado_service
from ..models import Rol, Sesionusuario, Logactividad, UserMetadata
from .serializers import (
    RolSerializer, SesionusuarioSerializer, LogactividadSerializer,
    UserMetadataSerializer, UserMetadataCreateSerializer
)

class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all().order_by("id")
    serializer_class = RolSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def perform_destroy(self, instance):
        instance.activo = False
        instance.save()

class EmpleadoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = UserMetadata.objects.select_related('user', 'rol', 'almacen_asignado').all()
        # Filtro por query params
        estado = self.request.query_params.get('es_activo')
        if estado is not None:
            queryset = queryset.filter(user__is_active=estado.lower() in ['true', '1'])
        return queryset

    def get_serializer_class(self):
        return UserMetadataCreateSerializer if self.action == 'create' else UserMetadataSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Lógica de extracción de datos para el servicio
        user_fields = ['username', 'password', 'email', 'first_name', 'last_name']
        user_data = {f: serializer.validated_data.pop(f, '') for f in user_fields if f in serializer.validated_data}
        
        metadata = crear_empleado_service(user_data, serializer.validated_data)

        read_serializer = UserMetadataSerializer(metadata, context={'request': request})
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)