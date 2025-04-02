from django.shortcuts import render

from .models import Producto
from django.http.response import JsonResponse
from http import HTTPStatus
from rest_framework.views import APIView  
from rest_framework import status
from .serializers import *
# Create your views here.

#Productos por id
class ProductoGet(APIView):
    
    def get(self, request, id):
        try:
            data = Producto.objects.get(id=id)
            serializer = ProductoSerializer(data)
            return JsonResponse({"data":serializer.data}, status=HTTPStatus.OK)
        except Exception as e:
            return JsonResponse({"estado":"error","mensaje":"Productos no encontrados"}, status=HTTPStatus.NOT_FOUND)

#Listar todos los productos	
class ProductoList(APIView):

	def get(self, request):
		productos = Producto.objects.filter(activo=True)
		serializer = ProductoSerializer(productos, many=True)

		return JsonResponse({"productos":serializer.data}, status=HTTPStatus.OK)
    
class ProductoCreateUpdateDelete(APIView):
	
	def post(self, request):
		serializer = ProductoSerializer(data=request.data)
		if serializer.is_valid():
		#Si el serializer es valido guardar el serializer o crearlo
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		
		
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)


	def put(self, request, id):
		try:	
			producto = Producto.objects.get(id=id)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},status=HTTPStatus.NOT_FOUND)
		
		serializer = ProductoSerializer(producto, data=request.data, partial=True)

		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
			
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)


	def delete(self, request, id):
		#Verificar si el producto existe
		try:
			producto = Producto.objects.get(id=id,activo=True)
		#No borrar el producto si no ponerlo como inactivo al encontrarlo
			producto.activo = False
			producto.save()			
			return JsonResponse({"estado":"eliminado","mensaje":"Producto inactivo"},status=HTTPStatus.OK)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},status=HTTPStatus.NOT_FOUND)

        
class ObtenerclienteAPIView(APIView):
	
	def get(self, request, id):
		try:
			data = Cliente.objects.get(id=id)
			serializer = ClienteSerializer(data)
			return JsonResponse({"estado":"ok","mensaje":serializer.data},status=status.HTTP_200_OK)
		except Cliente.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=status.HTTP_404_NOT_FOUND)	


class ClienteList(APIView):

	def get(self, request):
		clientes = Cliente.objects.filter(activo=True)
		serializer = ClienteSerializer(clientes, many=True)

		return JsonResponse({"clientes":serializer.data}, status=HTTPStatus.OK)

class ClienteCreateUpdateDelete(APIView):

	def post(self, request):
		serializer = ClienteSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=status.HTTP_201_CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=status.HTTP_400_BAD_REQUEST)
		
		
	def put(self, request, id):
		try:
			cliente = Cliente.objects.get(id=id)
			serializer = ClienteSerializer(cliente, data=request.data, partial=True)		
		except Cliente.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Cliente no encontrado"},status=status.HTTP_400_NOT_FOUND)

		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=status.HTTP_400_BAD_REQUEST)

	def delete(self, request, id):			
		try:
			cliente = Cliente.objects.get(id=id, estado=True)
			cliente.estado = False
			cliente.save()
			return JsonResponse({"estado":"eliminado","mensaje":"Cliente inactivo"},status=status.HTTP_200_OK)
		except Cliente.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Cliente no encontrado"},status=status.HTTP_404_NOT_FOUND)
