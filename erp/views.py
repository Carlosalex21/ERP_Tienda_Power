from django.shortcuts import render

from backend.models import Producto # type: ignore
from django.http.response import JsonResponse
from http import HTTPStatus
from rest_framework import APIView  # type: ignore
from .serializers import *
# Create your views here.

class Producto(APIView):
    
    def get(self, request, id):
        try:
            data = Producto.objects.filter(id=id).get()
            serializer = ProductoSerializer(data)
            return JsonResponse({"data":{"id":serializer.id,"nombre":serializer.nombre, "descripcion":serializer.descripcion, "precio":serializer.precio,"codigo_barras":serializer.codigo_barras, "descuento":serializer.descuento,"peso":serializer.peso,"dimensiones":serializer.dimensiones }}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"estado":"error","mensaje":"Productos no encontrados"}, HTTPStatus.NOT_FOUND)
    
class ProductoCreate(APIView):
	
	def POST(self, request):
		serializer = ProductoSerializer(data=request.data)
		if serializer.is_valid():
		#Si el serializer es valido guardar el serializer o crearlo
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},HTTPStatus.CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},HTTPStatus.BAD_REQUEST)


	def PUT(self, request, id):
		try:	
			producto = Producto.objects.get(id=id)
			serializer = ProductoSerializer(producto, data=request.data, partial=True)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},HTTPStatus.NOT_FOUND)

		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},HTTPStatus.OK)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},HTTPStatus.BAD_REQUEST)


	def delete(self, request, id):
		#Verificar si el producto existe
		try:
			producto = Producto.objects.get(id=id,estado=True)
		#No borrar el producto si no ponerlo como inactivo al encontrarlo
			producto.estado = False
			producto.save()			
			return JsonResponse({"estado":"eliminado","mensaje":"Producto inactivo"},status=HTTPStatus.OK)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},HTTPStatus.NOT_FOUND)

        
