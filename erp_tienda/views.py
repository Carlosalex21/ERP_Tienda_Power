from django.shortcuts import render

from backend.models import Cliente # type: ignore
from django.http.JsonResponse import JsonResponse
from django.http import status 
from rest_framework import APIView  # type: ignore
# Create your views here.

class Clase1(APIView):
    
    def get(self, request):
        data = Cliente.objects.filter(id=id).get()
        return JsonResponse({"estado":"ok","mensaje":"Cliente filtrado"})
    
        
