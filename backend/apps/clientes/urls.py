from django.urls import path
from .api.views import *

urlpatterns = [
    path("cliente/", ClienteList.as_view()),
    path("cliente/<int:id>/", ObtenerclienteAPIView.as_view()),
    path("cliente/crear/", ClienteCreateUpdateDelete.as_view()),
    path("cliente/editar/<int:id>/", ClienteCreateUpdateDelete.as_view()),
    path("cliente/eliminar/<int:id>/", ClienteCreateUpdateDelete.as_view()),
]