from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api.views import (
    ClienteListCreateView, ClienteRetrieveUpdateDestroyView,
    ClienteBulkUploadView, ClienteBulkUploadTemplateView, TiposDocumentoView,
)
from .api.views_b2b import (
    ClienteB2BBulkUploadView,
    B2BAccountActivationView,
    ClienteB2BProfileView,
    B2BCatalogoView,
    B2BCrearPedidoView,
    B2BSugerenciasReposicionView,
    NivelPrecioAdminViewSet,
    ClienteB2BAdminViewSet,
)

router = DefaultRouter()
router.register(r'b2b/niveles-precio', NivelPrecioAdminViewSet, basename='b2b-nivel-precio')
router.register(r'b2b/clientes', ClienteB2BAdminViewSet, basename='b2b-cliente-admin')

urlpatterns = [
    # --- Endpoints para Clientes Retail ---
    path('', ClienteListCreateView.as_view(), name='cliente-list-create'),
    path('tipos-documento/', TiposDocumentoView.as_view(), name='cliente-tipos-documento'),
    path('bulk-upload/', ClienteBulkUploadView.as_view(), name='cliente-bulk-upload'),
    path('bulk-upload/plantilla/', ClienteBulkUploadTemplateView.as_view(), name='cliente-bulk-upload-plantilla'),
    path('<int:pk>/', ClienteRetrieveUpdateDestroyView.as_view(), name='cliente-detail'),

    # --- Endpoints para Clientes B2B ---
    path('b2b/bulk-upload/', ClienteB2BBulkUploadView.as_view(), name='b2b-bulk-upload'),
    path('b2b/activate-account/', B2BAccountActivationView.as_view(), name='b2b-activate-account'),
    path('b2b/profile/', ClienteB2BProfileView.as_view(), name='b2b-profile'),
    path('b2b/catalogo/', B2BCatalogoView.as_view(), name='b2b-catalogo'),
    path('b2b/pedidos/', B2BCrearPedidoView.as_view(), name='b2b-crear-pedido'),
    path('b2b/sugerencias-reposicion/', B2BSugerenciasReposicionView.as_view(), name='b2b-sugerencias-reposicion'),

    # --- Endpoints de administración B2B (tenant admin) ---
    path('', include(router.urls)),
]
