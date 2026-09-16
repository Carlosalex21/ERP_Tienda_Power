from rest_framework.routers import DefaultRouter

from .api.views import RegistroAuditoriaViewSet

router = DefaultRouter()
router.register(r'registros', RegistroAuditoriaViewSet, basename='registro-auditoria')

urlpatterns = router.urls
