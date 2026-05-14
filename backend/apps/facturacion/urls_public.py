from django.urls import path
from .api.views_public import PublicProductCatalogView, PublicCreateOrderView

urlpatterns = [
    path('catalogo/', PublicProductCatalogView.as_view(), name='public-catalog'),
    path('ordenar/', PublicCreateOrderView.as_view(), name='public-create-order'),
]