from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .api.views_auth import CustomTokenObtainPairView
from .api.views_users import EmpleadoViewSet, RolViewSet, SesionusuarioViewSet, LogactividadViewSet

router = DefaultRouter()
router.register(r'empleados', EmpleadoViewSet, basename='empleado')
router.register(r'roles', RolViewSet, basename='rol')
router.register(r'sesiones', SesionusuarioViewSet, basename='sesion')
router.register(r'logs', LogactividadViewSet, basename='log')

urlpatterns = [
    # JWT Tokens
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Gestión de Usuarios
    path('usuarios/', UserMetadataListCreateView.as_view(), name='usuarios-list-create'),
    path('usuarios/<int:pk>/', UserMetadataDetailView.as_view(), name='usuarios-detail'),
    path('users/me/', UserMeView.as_view(), name='user-me'),
    
    # Roles
    path('roles/', RolList.as_view(), name='roles'),
]