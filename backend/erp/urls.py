from django.urls import path
from .views import *

urlpatterns = [
    path("producto", ProductoList.as_view()),
    path("producto/<int:id>", ProductoGet.as_view()),
    path("producto/crear", ProductoCreateUpdateDelete.as_view()),
    path("producto/editar/<int:id>", ProductoCreateUpdateDelete.as_view()),
    path("producto/eliminar/<int:id>", ProductoCreateUpdateDelete.as_view()),
    #tabla Cliente
    path("cliente", ClienteList.as_view()),
    path("cliente/<int:id>", ObtenerclienteAPIView.as_view()),
    path("cliente/crear", ClienteCreateUpdateDelete.as_view()),
    path("cliente/editar/<int:id>", ClienteCreateUpdateDelete.as_view()),
    path("cliente/eliminar/<int:id>", ClienteCreateUpdateDelete.as_view()),
]
