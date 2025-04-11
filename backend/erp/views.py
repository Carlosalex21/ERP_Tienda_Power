from django.shortcuts import render

from .models import *
from django.http.response import JsonResponse
from http import HTTPStatus
from rest_framework.views import APIView  
from rest_framework import status
from .serializers import ProductoSerializer, ClienteSerializer, CategoriaSerializer, AlmacenSerializer, InventarioSerializer, UserMetadataSerializer
from django.contrib.auth import aunthenticate
# Create your views here.


class UserCRUD(APIView):

	def post(self, request):
		user = User.objects.create_user(username=request.data.get("email"), password=request.data.get("password"))
		serializer = UserMetadataSerializer(user)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		
		
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
	
	def put(self, request, id):
		try:
			user = User.objects.get(id=id)
		except User.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Usuario no encontrado"},status=HTTPStatus.NOT_FOUND)
		
		serializer = UserMetadataSerializer(user, request=request.data, partial=True)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
			
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
	
	def delete(self, request, id):
		try:
			user = User.objects.get(id=id, is_active=True)
			user.is_active=False
			user.save()
			return JsonResponse({"estado":"eliminado","mensaje":"Producto inactivo"},status=HTTPStatus.OK)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},status=HTTPStatus.NOT_FOUND)
		


class UserLogin(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        # Autenticar al usuario
        user = aunthenticate(username=email, password=password)
        
        if user is not None:
            return JsonResponse({
                "estado": "success",
                "mensaje": "Inicio de sesión exitoso",
                "user_id": user.id,
                "email": user.email,
                "username": user.username
            }, status=HTTPStatus.OK)
        else:
            return JsonResponse({
                "estado": "error",
                "mensaje": "Credenciales inválidas"
            }, status=HTTPStatus.UNAUTHORIZED)


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
		productos = Producto.objects.filter(activo=True).order_by("id")
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



class AlmacenGet(APIView):

	def get(self, request, id):
		try:
			data = Almacen.objects.get(id=id)
			serializer = AlmacenSerializer(data)
			return JsonResponse({"data":serializer.data}, status=HTTPStatus.OK)
		except Exception as e:
			return JsonResponse({"estado":"error","mensaje":"Almacen no encontrado"}, status=HTTPStatus.NOT_FOUND)


class AlmacenList(APIView):

	def get(self, request):
		almacen = Almacen.objects.filter(activo=True).order_by("id")
		serializer = AlmacenSerializer(almacen, many=True)

		return JsonResponse({"almacenes":serializer.data}, status=HTTPStatus.OK)

class AlmacenCRUD(APIView):

	def post(self, request):
		serializer = AlmacenSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
		
	def put(self, request, id):
		try:
			almacen = Almacen.objects.get(id=id)
		except Almacen.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Almacen no encontrado"},status=HTTPStatus.NOT_FOUND)

		serializer = AlmacenSerializer(almacen, data=request.data, partial=True)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
		
	def delete(self, request, id):
		try:
			almacen = Almacen.objects.get(id=id, activo=True)
			almacen.activo = False
			almacen.save()
			return JsonResponse({"estado":"eliminado","mensaje":"almacen inactivo"},status=HTTPStatus.OK)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Almacen no encontrado"},status=HTTPStatus.NOT_FOUND)


class InventarioGet(APIView):
	def get(self, request, id):
		try:
			data = Inventario.objects.get(id=id)
			serializer = InventarioSerializer(data)
			return JsonResponse({"data":serializer.data}, status=HTTPStatus.OK)
		except Exception as e:
			return JsonResponse({"estado":"error","mensaje":"Inventario no encontrado"}, status=HTTPStatus.NOT_FOUND) 

class InventarioList(APIView):
	def get(self, request):
		data = Inventario.objects.filter(activo=True).order_by("id")
		serializer = InventarioSerializer(data, many=True)
		return JsonResponse({"data":serializer.data}, status=HTTPStatus.OK)


class InventarioCrud(APIView):
	
	def post(self, request):
		serializer = InventarioSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
		
	def put(self, request, id):
		try:
			data = Inventario.objects.get(id=id)
		except Inventario.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Inventario no encontrado"},status=HTTPStatus.NOT_FOUND)

		serializer = InventarioSerializer(data, request=request.data, partial=True)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
			
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
	

	def delete(self, request, id):
		try:
			data = Inventario.objects.get(id=id, activo=True)
			data.activo = False
			data.save()
			return JsonResponse({"estado":"eliminado","mensaje":"Inventario inactivo"},status=HTTPStatus.OK)
		except Inventario.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Inventario no encontrado"},status=HTTPStatus.NOT_FOUND)


class CategoriaGet(APIView):

	def get(self, request, id):
		try:
			data = Categoriaproducto.objects.get(id=id)
			serializer = CategoriaSerializer(data)
			return JsonResponse({"data":serializer.data}, status=HTTPStatus.OK)
		except Exception as e:
			return JsonResponse({"estado":"error","mensaje":"Categoria no encontrada"}, status=HTTPStatus.NOT_FOUND)


class CategoriaList(APIView):
	
	def get(self, request):
		categoria = Categoriaproducto.objects.filter(activo=True).order_by("id")
		serializer = CategoriaSerializer(categoria, many=True)
		return JsonResponse({"categorias":serializer.data}, status=HTTPStatus.OK)


class CategoriaCrud(APIView):

	def post(self, request):
		serializer = CategoriaSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
		
	def put(self, request, id):
		try:
			categoria = Categoriaproducto.objects.get(id=id)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Producto no encontrado"},status=HTTPStatus.NOT_FOUND)	
		
		serializer = CategoriaSerializer(categoria, data=request.data, partial=True)

		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
			
		return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
	
	def delete(self, request, id):
		try:
			categoria = Categoriaproducto.objects.get(id=id,activo=True)
			categoria.activo = False
			categoria.save()
			return JsonResponse({"estado":"eliminado","mensaje":"Categoria inactiva"},status=HTTPStatus.OK)
		except Producto.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Categoria no encontrado"},status=HTTPStatus.NOT_FOUND)


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
		clientes = Cliente.objects.filter(activo=True).order_by("id")
		serializer = ClienteSerializer(clientes, many=True)

		return JsonResponse({"clientes":serializer.data}, status=HTTPStatus.OK)

class ClienteCreateUpdateDelete(APIView):

	def post(self, request):
		serializer = ClienteSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"creado","data":serializer.data},status=HTTPStatus.CREATED)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)
		
		
	def put(self, request, id):
		try:
			cliente = Cliente.objects.get(id=id)
			serializer = ClienteSerializer(cliente, data=request.data, partial=True)		
		except Cliente.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Cliente no encontrado"},status=HTTPStatus.NOT_FOUND)

		if serializer.is_valid():
			serializer.save()
			return JsonResponse({"estado":"actualizado","data":serializer.data},status=HTTPStatus.OK)
		else:
			return JsonResponse({"estado":"error","mensaje":serializer.errors},status=HTTPStatus.BAD_REQUEST)

	def delete(self, request, id):			
		try:
			cliente = Cliente.objects.get(id=id, activo=True)
			cliente.activo = False
			cliente.save()
			return JsonResponse({"estado":"eliminado","mensaje":"Cliente inactivo"},status=HTTPStatus.OK)
		except Cliente.DoesNotExist:
			return JsonResponse({"estado":"error","mensaje":"Cliente no encontrado"},status=HTTPStatus.NOT_FOUND)
