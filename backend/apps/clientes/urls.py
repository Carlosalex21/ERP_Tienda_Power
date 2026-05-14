from django.urls import path
from .api.views import ClienteListCreateView, ClienteRetrieveUpdateDestroyView

urlpatterns = [
    path('', ClienteListCreateView.as_view(), name='cliente-list-create'),
    path('<int:pk>/', ClienteRetrieveUpdateDestroyView.as_view(), name='cliente-detail'),
]