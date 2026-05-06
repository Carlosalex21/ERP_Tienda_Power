from django.urls import path
# from .views import *

urlpatterns = [
    path("tipos-documento/", TipodocumentofiscalList.as_view(), name='tipos-documentos'),
    path("correlativo/", ConfiguracionCorrelativoManageView.as_view()),
    path("iva/", ConfiguracionivaList.as_view()),
    path("iva/<int:id>/", ConfiguracionivaGet.as_view()),
    path("iva/crear/", ConfiguracionivaCRUD.as_view()),
    path("iva/editar/<int:id>/", ConfiguracionivaCRUD.as_view()),
    path("iva/eliminar/<int:id>/", ConfiguracionivaCRUD.as_view()),
]