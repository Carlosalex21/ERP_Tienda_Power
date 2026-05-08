from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .api.views_auth import CustomTokenObtainPairView
from .api.views_users import EmpleadoViewSet, RolViewSet

router = DefaultRouter()
router.register(r'empleados', EmpleadoViewSet, basename='empleado')
router.register(r'roles', RolViewSet, basename='rol')

urlpatterns = [
    # API viewsets
    path('', include(router.urls)),

    # JWT Tokens
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]