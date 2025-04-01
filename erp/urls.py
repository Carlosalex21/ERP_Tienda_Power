from django.urls import path
from .views import *

urlpatterns = [
    path("/producto", ProductoCreate.as_view()),
]
