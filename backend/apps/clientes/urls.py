from django.urls import path
from .api.views import ClienteListCreateView, ClienteRetrieveUpdateDestroyView
from .api.views_b2b import ClienteB2BBulkUploadView, B2BAccountActivationView, ClienteB2BProfileView

urlpatterns = [
    # --- Endpoints para Clientes Retail ---
    path('', ClienteListCreateView.as_view(), name='cliente-list-create'),
    path('<int:pk>/', ClienteRetrieveUpdateDestroyView.as_view(), name='cliente-detail'),

    # --- Endpoints para Clientes B2B ---
    path('b2b/bulk-upload/', ClienteB2BBulkUploadView.as_view(), name='b2b-bulk-upload'),
    path('b2b/activate-account/', B2BAccountActivationView.as_view(), name='b2b-activate-account'),
    path('b2b/profile/', ClienteB2BProfileView.as_view(), name='b2b-profile'),
]