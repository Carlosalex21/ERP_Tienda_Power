from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views_auth import CustomTokenObtainPairView, UserMeView
from .api.views_management import UserManagementViewSet

router = DefaultRouter()
router.register(r'management', UserManagementViewSet, basename='user-management')

urlpatterns = [
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('me/', UserMeView.as_view(), name='user-me'),
    # Rutas para que el admin del tenant gestione a sus usuarios
    path('', include(router.urls)),
]