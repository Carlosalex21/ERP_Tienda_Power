from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .api.views_auth import CustomTokenObtainPairView, UserMeView, CambiarPasswordView
from .api.views_password_reset import PasswordResetRequestView, PasswordResetConfirmView
from .api.views_management import UserManagementViewSet
from .api.views_roles import RolViewSet
from .api.views_vendedores import VendedoresListView
from .api.views_login_attempts import LoginAttemptViewSet

router = DefaultRouter()
router.register(r'management', UserManagementViewSet, basename='user-management')
# Antes no existía ninguna ruta para RolViewSet (vivía en views_users.py sin
# registrar): el frontend de RRHH hardcodeaba 3 roles con IDs fijos (1, 2, 3)
# en vez de consultar los roles reales del tenant.
router.register(r'roles', RolViewSet, basename='rol')
router.register(r'login-attempts', LoginAttemptViewSet, basename='login-attempt')

urlpatterns = [
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    # Antes NO existía esta ruta para el esquema de un tenant (solo en el
    # esquema público) -- cualquier sesión de más de 15 minutos (vida del
    # access token) en el panel de un tenant se rompía en silencio porque
    # el refresh siempre devolvía 404.
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserMeView.as_view(), name='user-me'),
    path('me/cambiar-password/', CambiarPasswordView.as_view(), name='user-cambiar-password'),
    path('vendedores/', VendedoresListView.as_view(), name='vendedores-list'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    # Rutas para que el admin del tenant gestione a sus usuarios
    path('', include(router.urls)),
]