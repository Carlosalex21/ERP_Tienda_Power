from django.shortcuts import render

from .models import *
from django.utils import timezone
from decimal import Decimal
import csv
from datetime import datetime
from django.http.response import JsonResponse, HttpResponse
from http import HTTPStatus
from rest_framework.views import APIView  
from rest_framework import status
from .serializers import (ProductoSerializer, ClienteSerializer, CategoriaSerializer, AlmacenSerializer, InventarioSerializer, UserMetadataSerializer, ConfiguracionivaSerializer, CupondescuentoSerializer, DetallefacturaSerializer,DevolucionSerializer, FacturaSerializer, FacturaelectronicaSerializer, MovimientoInventarioSerializer, LecturacodigobarrasSerializer, LogactividadSerializer, OrdenSerializer,ProductocategoriaSerializer, ProveedorSerializer, ReporteclienteSerializer, ReporteinventarioSerializer, ReporteventaSerializer, ReservastockSerializer, RolSerializer, SesionusuarioSerializer, TipodocumentofiscalSerializer,TransaccionpagoSerializer, VariacionproductoSerializer)
from django.contrib.auth import authenticate, get_user_model


User = get_user_model()  # Esto utiliza el modelo de usuario de Django.

# ------------------------------------------------------------------------------
# Registro de usuario minimal (solo correo, password y rol)
# ------------------------------------------------------------------------------
class UserRegistration(APIView):
    def post(self, request):
        # Se reciben los campos mínimos: email, password y rol (en este ejemplo, el ID del rol)
        email = request.data.get("email")
        password = request.data.get("password")
        rol_id = request.data.get("rol")  # Se espera que sea el ID del rol
        
        # Validamos que estos campos no sean nulos.
        if not email or not password or not rol_id:
            return JsonResponse({
                "estado": "error",
                "mensaje": "Email, password y rol son requeridos."
            }, status=HTTPStatus.BAD_REQUEST)
        
        # Se crea al usuario; en este ejemplo, usamos el email como username.
        try:
            user = User.objects.create_user(username=email, email=email, password=password)
        except Exception as e:
            return JsonResponse({
                "estado": "error",
                "mensaje": f"No se pudo crear el usuario: {str(e)}"
            }, status=HTTPStatus.BAD_REQUEST)
        
        # Obtenemos el rol (asegúrate de que el rol exista).
        try:
            rol = Rol.objects.get(id=rol_id)
        except Rol.DoesNotExist:
            return JsonResponse({
                "estado": "error",
                "mensaje": "No se encontró el rol indicado."
            }, status=HTTPStatus.BAD_REQUEST)
        
        # Creamos una entrada mínima en la tabla UserMetadata (solo con el rol).
        UserMetadata.objects.create(user=user, rol=rol)
        
        return JsonResponse({
            "estado": "creado",
            "user": {
                "id": user.id,
                "email": user.email,
                "rol": rol.nombre  # O el campo que consideres representativo.
            }
        }, status=HTTPStatus.CREATED)

# ------------------------------------------------------------------------------
# Actualización del perfil completo (completar los demás campos de UserMetadata)
# ------------------------------------------------------------------------------
class UserProfileUpdate(APIView):
     def put(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({
                "estado": "error",
                "mensaje": "Usuario no encontrado."}, status=HTTPStatus.NOT_FOUND)
        metadata, created = UserMetadata.objects.update_or_create(user=user, defaults=request.data)
        serializer = UserMetadataSerializer(metadata)
        return JsonResponse({
        	"estado": "actualizado" if not created else "creado",
        	"data": serializer.data}, status=HTTPStatus.OK)
            
	
# ------------------------------------------------------------------------------
# Login (para autenticar usando email y password)

class UserLogin(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        
        user = authenticate(username=email, password=password)
        
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


class UserDelete(APIView):
     
	 def delete(self, request, user_id):
           try:
                user = User.objects.get(id=user_id, is_active=True)
                user.is_active = False
                user.save()
                return JsonResponse({"estado": "Inactivo", "mensaje": "Usuario inactivo"}, status=HTTPStatus.OK)
           except User.DoesNotExist:
                return JsonResponse({"estado":"error","mensaje":"Usuario no encontrado"}, status=HTTPStatus.NOT_FOUND)

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


# ==============
# Logica Escanear producto y mostrarlo en el template
# ==============
def agg_producto_a_orden(cliente_id, barcode, cantidad=1):
    # Buscar el producto por código de barras
    try:
        producto = Producto.objects.get(codigo_barras=barcode)
    except Producto.DoesNotExist:
        return None, "Producto no encontrado para este código."
    
    inventario = Inventario.objects.filter(producto=producto, activo=True).first()
    if not inventario:
        return None, "No existe registro de inventario para este producto."
    
    detalle_existente = Detallefactura.objects.filter(
         factura__cliente_id = cliente_id,
         producto = producto,
         factura__estado = "abierta"
    ).first()

    cantidad_existente = detalle_existente.cantidad if detalle_existente else 0
    total_solicitada = cantidad_existente + cantidad

    if total_solicitada > inventario.cantidad:
         return None, f"La cantidad solicitada ({total_solicitada}) excede el stock disponible ({inventario.cantidad})."
    
    # Buscar u obtener la orden activa para ese cliente.
    orden = Orden.objects.filter(cliente_id=cliente_id, estado="abierta", activo=True).first()
    if not orden:
        orden = Orden.objects.create(
            cliente_id=cliente_id,
            estado="abierta",
            fecha_operacion=timezone.now(),
            metodo_pago="",
            subtotal=Decimal('0.00'),
            descuento_total=Decimal('0.00'),
            iva_total=Decimal('0.00'),
            total=Decimal('0.00'),
            direccion_envio="",
            correlativo="T-" + timezone.now().strftime("%Y%m%d%H%M%S")
        )
         

    # Agregar o actualizar el detalle de la orden
    detalle, created = Detallefactura.objects.get_or_create(
        factura=orden,
        producto=producto,
        defaults={
            "cantidad": cantidad,
            "precio_unitario": producto.precio,
            "descuento": Decimal('0.00'),
            "subtotal_linea": producto.precio * cantidad,
            "iva_linea": producto.precio * cantidad * Decimal('0.12'),
            "total_linea": producto.precio * cantidad + (producto.precio * cantidad * Decimal('0.12')),
        }
    )
    if not created:
        detalle.cantidad += cantidad
        detalle.subtotal_linea = detalle.cantidad * detalle.precio_unitario - (detalle.descuento or Decimal('0.00'))
        detalle.iva_linea = detalle.subtotal_linea * Decimal('0.12')
        detalle.total_linea = detalle.subtotal_linea + detalle.iva_linea
        detalle.save()
    
    # Recalcular totales de la orden
    detalles = Detallefactura.objects.filter(factura=orden)
    orden.subtotal = sum(d.subtotal_linea for d in detalles)
    orden.iva_total = sum(d.iva_linea for d in detalles)
    orden.total = sum(d.total_linea for d in detalles)
    orden.save()

    return orden, None

# Endpoint que utiliza la función anterior:
class BarcodeScanView(APIView):
    def post(self, request):
        cliente_id = request.data.get("cliente_id")
        barcode = request.data.get("codigo_barras")
        cantidad = int(request.data.get("cantidad", 1))
        if not cliente_id or not barcode:
            return JsonResponse({
                "estado": "error",
                "mensaje": "Se requiere cliente_id y código de barras."
            }, status=HTTPStatus.BAD_REQUEST)
        
        orden, error = agg_producto_a_orden(cliente_id, barcode, cantidad)
        if error:
            return JsonResponse({"estado": "error", "mensaje": error}, status=HTTPStatus.NOT_FOUND)
        
        # Retornar la orden actualizada
        return JsonResponse({
            "estado": "success",
            "mensaje": "Producto agregado/actualizado en la orden.",
            "orden": {
                "id": orden.id,
                "subtotal": str(orden.subtotal),
                "iva_total": str(orden.iva_total),
                "total": str(orden.total)
            }
        }, status=HTTPStatus.OK)



# =========================================================
# PRODUCTO CATEGORIA
# =========================================================
class ProductocategoriaGet(APIView):
    def get(self, request, id):
        try:
            obj = Productocategoria.objects.get(id=id)
            serializer = ProductocategoriaSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Productocategoria.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ProductoCategoria no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

class ProductocategoriaList(APIView):
    def get(self, request):
        queryset = Productocategoria.objects.all().order_by("id")
        serializer = ProductocategoriaSerializer(queryset, many=True)
        return JsonResponse({"producto_categoria": serializer.data}, status=HTTPStatus.OK)

class ProductocategoriaCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = ProductocategoriaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Productocategoria.objects.get(id=id)
        except Productocategoria.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ProductoCategoria no encontrada"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = ProductocategoriaSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Productocategoria.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "ProductoCategoria eliminada"},
                                status=HTTPStatus.OK)
        except Productocategoria.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ProductoCategoria no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# PROVEEDOR
# =========================================================
class ProveedorGet(APIView):
    def get(self, request, id):
        try:
            obj = Proveedor.objects.get(id=id)
            serializer = ProveedorSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Proveedor.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Proveedor no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

class ProveedorList(APIView):
    def get(self, request):
        queryset = Proveedor.objects.all().order_by("id")
        serializer = ProveedorSerializer(queryset, many=True)
        return JsonResponse({"proveedores": serializer.data}, status=HTTPStatus.OK)

class ProveedorCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = ProveedorSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Proveedor.objects.get(id=id)
        except Proveedor.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Proveedor no encontrado"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = ProveedorSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Proveedor.objects.get(id=id, activo=True)
            obj.activo = False
            obj.save()
            return JsonResponse({"estado": "eliminado", "mensaje": "Proveedor eliminado"},
                                status=HTTPStatus.OK)
        except Proveedor.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Proveedor no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# REPORTES (Solo lectura) y EXPORTACIÓN CSV
# =========================================================

# --- Reportecliente: como no tiene campos de fecha, solo se listan y exportan todos ---
class ReporteclienteList(APIView):
    def get(self, request):
        queryset = Reportecliente.objects.all().order_by("id")
        serializer = ReporteclienteSerializer(queryset, many=True)
        return JsonResponse({"reporte_clientes": serializer.data}, status=HTTPStatus.OK)

class ReporteclienteExportCSV(APIView):
    def get(self, request):
        queryset = Reportecliente.objects.all().order_by("id")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="reporte_clientes.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Cliente", "Total Compras", "Cantidad Pedidos", "Producto Mas Comprado"])
        for reporte in queryset:
            cliente = reporte.cliente if reporte.cliente else ""
            prod_mc = reporte.producto_mas_comprado if reporte.producto_mas_comprado else ""
            writer.writerow([reporte.id, cliente, reporte.total_compras, reporte.cantidad_pedidos, prod_mc])
        return response

# --- Reporteinventario ---
class ReporteinventarioList(APIView):
    def get(self, request):
        queryset = Reporteinventario.objects.all().order_by("id")
        serializer = ReporteinventarioSerializer(queryset, many=True)
        return JsonResponse({"reporte_inventario": serializer.data}, status=HTTPStatus.OK)

class ReporteinventarioExportCSV(APIView):
    def get(self, request):
        # Filtrado opcional por fecha: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        queryset = Reporteinventario.objects.all()
        if start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                queryset = queryset.filter(fecha__range=(start_date_obj, end_date_obj))
            except ValueError:
                return JsonResponse({"estado": "error", "mensaje": "Formato de fecha incorrecto, use YYYY-MM-DD"},
                                    status=HTTPStatus.BAD_REQUEST)
        queryset = queryset.order_by("id")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="reporte_inventario.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Fecha", "Producto", "Stock Inicial", "Stock Final", "Movimientos", "Almacen"])
        for reporte in queryset:
            producto = reporte.producto if reporte.producto else ""
            almacen = reporte.almacen if reporte.almacen else ""
            writer.writerow([reporte.id, reporte.fecha, producto, reporte.stock_inicial,
                             reporte.stock_final, reporte.movimientos, almacen])
        return response

# --- Reporteventa ---
class ReporteventaList(APIView):
    def get(self, request):
        queryset = Reporteventa.objects.all().order_by("id")
        serializer = ReporteventaSerializer(queryset, many=True)
        return JsonResponse({"reporte_venta": serializer.data}, status=HTTPStatus.OK)

class ReporteventaExportCSV(APIView):
    def get(self, request):
        # Filtrado opcional por fecha: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        queryset = Reporteventa.objects.all()
        if start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                queryset = queryset.filter(fecha__range=(start_date_obj, end_date_obj))
            except ValueError:
                return JsonResponse({"estado": "error", "mensaje": "Formato de fecha incorrecto, use YYYY-MM-DD"},
                                    status=HTTPStatus.BAD_REQUEST)
        queryset = queryset.order_by("id")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="reporte_venta.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Fecha", "Total Ventas", "Total IVA", "Total Descuentos",
                         "Cantidad Transacciones", "Almacen"])
        for reporte in queryset:
            almacen = reporte.almacen if reporte.almacen else ""
            writer.writerow([reporte.id, reporte.fecha, reporte.total_ventas, reporte.total_iva,
                             reporte.total_descuentos, reporte.cantidad_transacciones, almacen])
        return response

# =========================================================
# RESERVA STOCK
# =========================================================
class ReservastockGet(APIView):
    def get(self, request, id):
        try:
            obj = Reservastock.objects.get(id=id)
            serializer = ReservastockSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Reservastock.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ReservaStock no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

class ReservastockList(APIView):
    def get(self, request):
        queryset = Reservastock.objects.all().order_by("id")
        serializer = ReservastockSerializer(queryset, many=True)
        return JsonResponse({"reserva_stock": serializer.data}, status=HTTPStatus.OK)

class ReservastockCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = ReservastockSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Reservastock.objects.get(id=id)
        except Reservastock.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ReservaStock no encontrada"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = ReservastockSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Reservastock.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "ReservaStock eliminada"},
                                status=HTTPStatus.OK)
        except Reservastock.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "ReservaStock no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# ROL
# =========================================================
class RolGet(APIView):
    def get(self, request, id):
        try:
            obj = Rol.objects.get(id=id)
            serializer = RolSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Rol.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Rol no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

class RolList(APIView):
    def get(self, request):
        queryset = Rol.objects.all().order_by("id")
        serializer = RolSerializer(queryset, many=True)
        return JsonResponse({"roles": serializer.data}, status=HTTPStatus.OK)

class RolCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = RolSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Rol.objects.get(id=id)
        except Rol.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Rol no encontrado"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = RolSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Rol.objects.get(id=id, activo=True)
            obj.activo = False
            obj.save()
            return JsonResponse({"estado": "eliminado", "mensaje": "Rol eliminado"},
                                status=HTTPStatus.OK)
        except Rol.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Rol no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# SESION USUARIO
# =========================================================
class SesionusuarioGet(APIView):
    def get(self, request, id):
        try:
            obj = Sesionusuario.objects.get(id=id)
            serializer = SesionusuarioSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Sesionusuario.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "SesionUsuario no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

class SesionusuarioList(APIView):
    def get(self, request):
        queryset = Sesionusuario.objects.all().order_by("id")
        serializer = SesionusuarioSerializer(queryset, many=True)
        return JsonResponse({"sesiones": serializer.data}, status=HTTPStatus.OK)

class SesionusuarioCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = SesionusuarioSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creada", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Sesionusuario.objects.get(id=id)
        except Sesionusuario.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "SesionUsuario no encontrada"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = SesionusuarioSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizada", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Sesionusuario.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminada", "mensaje": "SesionUsuario eliminada"},
                                status=HTTPStatus.OK)
        except Sesionusuario.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "SesionUsuario no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# TIPO DOCUMENTO FISCAL
# =========================================================
class TipodocumentofiscalGet(APIView):
    def get(self, request, id):
        try:
            obj = Tipodocumentofiscal.objects.get(id=id)
            serializer = TipodocumentofiscalSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Tipodocumentofiscal.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TipoDocumentoFiscal no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

class TipodocumentofiscalList(APIView):
    def get(self, request):
        queryset = Tipodocumentofiscal.objects.all().order_by("id")
        serializer = TipodocumentofiscalSerializer(queryset, many=True)
        return JsonResponse({"tipos_documento": serializer.data}, status=HTTPStatus.OK)

class TipodocumentofiscalCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = TipodocumentofiscalSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Tipodocumentofiscal.objects.get(id=id)
        except Tipodocumentofiscal.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TipoDocumentoFiscal no encontrado"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = TipodocumentofiscalSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Tipodocumentofiscal.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "TipoDocumentoFiscal eliminado"},
                                status=HTTPStatus.OK)
        except Tipodocumentofiscal.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TipoDocumentoFiscal no encontrado"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# TRANSACCION PAGO
# =========================================================
class TransaccionpagoGet(APIView):
    def get(self, request, id):
        try:
            obj = Transaccionpago.objects.get(id=id)
            serializer = TransaccionpagoSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Transaccionpago.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TransaccionPago no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

class TransaccionpagoList(APIView):
    def get(self, request):
        queryset = Transaccionpago.objects.all().order_by("id")
        serializer = TransaccionpagoSerializer(queryset, many=True)
        return JsonResponse({"transacciones": serializer.data}, status=HTTPStatus.OK)

class TransaccionpagoCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = TransaccionpagoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creada", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Transaccionpago.objects.get(id=id)
        except Transaccionpago.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TransaccionPago no encontrada"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = TransaccionpagoSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizada", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Transaccionpago.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminada", "mensaje": "TransaccionPago eliminada"},
                                status=HTTPStatus.OK)
        except Transaccionpago.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "TransaccionPago no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

# =========================================================
# VARIACION PRODUCTO
# =========================================================
class VariacionproductoGet(APIView):
    def get(self, request, id):
        try:
            obj = Variacionproducto.objects.get(id=id)
            serializer = VariacionproductoSerializer(obj)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Variacionproducto.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "VariacionProducto no encontrada"},
                                status=HTTPStatus.NOT_FOUND)

class VariacionproductoList(APIView):
    def get(self, request):
        queryset = Variacionproducto.objects.all().order_by("id")
        serializer = VariacionproductoSerializer(queryset, many=True)
        return JsonResponse({"variaciones": serializer.data}, status=HTTPStatus.OK)

class VariacionproductoCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = VariacionproductoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            obj = Variacionproducto.objects.get(id=id)
        except Variacionproducto.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "VariacionProducto no encontrada"},
                                status=HTTPStatus.NOT_FOUND)
        serializer = VariacionproductoSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            obj = Variacionproducto.objects.get(id=id)
            obj.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "VariacionProducto eliminada"}, status=HTTPStatus.OK)
        except Variacionproducto.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "VariacionProducto no encontrada"}, status=HTTPStatus.NOT_FOUND)



# ==============================================================
# Configuración IVA
# ==============================================================
class ConfiguracionivaGet(APIView):
    def get(self, request, id):
        try:
            config = Configuracioniva.objects.get(id=id)
            serializer = ConfiguracionivaSerializer(config)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Configuracioniva.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "ConfiguracionIVA no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

class ConfiguracionivaList(APIView):
    def get(self, request):
        configs = Configuracioniva.objects.all().order_by("id")
        serializer = ConfiguracionivaSerializer(configs, many=True)
        return JsonResponse({"configuraciones": serializer.data}, status=HTTPStatus.OK)

class ConfiguracionivaCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = ConfiguracionivaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            config = Configuracioniva.objects.get(id=id)
        except Configuracioniva.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "ConfiguracionIVA no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = ConfiguracionivaSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            config = Configuracioniva.objects.get(id=id)
            config.delete()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "ConfiguracionIVA eliminada"},
                status=HTTPStatus.OK
            )
        except Configuracioniva.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "ConfiguracionIVA no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Cupón Descuento
# ==============================================================
class CupondescuentoGet(APIView):
    def get(self, request, id):
        try:
            cupon = Cupondescuento.objects.get(id=id)
            serializer = CupondescuentoSerializer(cupon)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Cupondescuento.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Cupón de descuento no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

class CupondescuentoList(APIView):
    def get(self, request):
        cupones = Cupondescuento.objects.all().order_by("id")
        serializer = CupondescuentoSerializer(cupones, many=True)
        return JsonResponse({"cupones": serializer.data}, status=HTTPStatus.OK)

class CupondescuentoCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = CupondescuentoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            cupon = Cupondescuento.objects.get(id=id)
        except Cupondescuento.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Cupón de descuento no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = CupondescuentoSerializer(cupon, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            cupon = Cupondescuento.objects.get(id=id)
            cupon.delete()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Cupón de descuento eliminado"},
                status=HTTPStatus.OK
            )
        except Cupondescuento.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Cupón de descuento no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Detalle Factura
# ==============================================================
class DetallefacturaGet(APIView):
    def get(self, request, id):
        try:
            detalle = Detallefactura.objects.get(id=id)
            serializer = DetallefacturaSerializer(detalle)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Detallefactura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Detalle de factura no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

class DetallefacturaList(APIView):
    def get(self, request):
        detalles = Detallefactura.objects.all().order_by("id")
        serializer = DetallefacturaSerializer(detalles, many=True)
        return JsonResponse({"detalles": serializer.data}, status=HTTPStatus.OK)

class DetallefacturaCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = DetallefacturaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            detalle = Detallefactura.objects.get(id=id)
        except Detallefactura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Detalle de factura no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = DetallefacturaSerializer(detalle, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            detalle = Detallefactura.objects.get(id=id)
            detalle.delete()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Detalle de factura eliminado"},
                status=HTTPStatus.OK
            )
        except Detallefactura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Detalle de factura no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Devolución
# ==============================================================
class DevolucionGet(APIView):
    def get(self, request, id):
        try:
            devolucion = Devolucion.objects.get(id=id)
            serializer = DevolucionSerializer(devolucion)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Devolucion.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Devolución no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

class DevolucionList(APIView):
    def get(self, request):
        devoluciones = Devolucion.objects.all().order_by("id")
        serializer = DevolucionSerializer(devoluciones, many=True)
        return JsonResponse({"devoluciones": serializer.data}, status=HTTPStatus.OK)

class DevolucionCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = DevolucionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            devolucion = Devolucion.objects.get(id=id)
        except Devolucion.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Devolución no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = DevolucionSerializer(devolucion, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            devolucion = Devolucion.objects.get(id=id, activo=True)
            devolucion.activo = False
            devolucion.save()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Devolución eliminada"},
                status=HTTPStatus.OK
            )
        except Devolucion.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Devolución no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Factura
# ==============================================================
class FacturaGet(APIView):
    def get(self, request, id):
        try:
            factura = Factura.objects.get(id=id)
            serializer = FacturaSerializer(factura)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Factura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

class FacturaList(APIView):
    def get(self, request):
        facturas = Factura.objects.all().order_by("id")
        serializer = FacturaSerializer(facturas, many=True)
        return JsonResponse({"facturas": serializer.data}, status=HTTPStatus.OK)

class FacturaCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = FacturaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            factura = Factura.objects.get(id=id)
        except Factura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = FacturaSerializer(factura, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            factura = Factura.objects.get(id=id, activo=True)
            factura.activo = False
            factura.save()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Factura eliminada"},
                status=HTTPStatus.OK
            )
        except Factura.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Factura Electrónica
# ==============================================================
class FacturaelectronicaGet(APIView):
    def get(self, request, id):
        try:
            fact_elec = Facturaelectronica.objects.get(id=id)
            serializer = FacturaelectronicaSerializer(fact_elec)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Facturaelectronica.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura electrónica no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

class FacturaelectronicaList(APIView):
    def get(self, request):
        fact_elems = Facturaelectronica.objects.all().order_by("id")
        serializer = FacturaelectronicaSerializer(fact_elems, many=True)
        return JsonResponse({"facturas_electronicas": serializer.data}, status=HTTPStatus.OK)

class FacturaelectronicaCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = FacturaelectronicaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            fact_elec = Facturaelectronica.objects.get(id=id)
        except Facturaelectronica.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura electrónica no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = FacturaelectronicaSerializer(fact_elec, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            fact_elec = Facturaelectronica.objects.get(id=id,activo=True)
            fact_elec.activo = False
            fact_elec.save()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Factura electrónica eliminada"},
                status=HTTPStatus.OK
            )
        except Facturaelectronica.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Factura electrónica no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Movimiento Inventario
# ==============================================================
class MovimientoInventarioGet(APIView):
    def get(self, request, id):
        try:
            movimiento = MovimientoInventario.objects.get(id=id)
            serializer = MovimientoInventarioSerializer(movimiento)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except MovimientoInventario.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Movimiento de inventario no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

class MovimientoInventarioList(APIView):
    def get(self, request):
        movimientos = MovimientoInventario.objects.all().order_by("id")
        serializer = MovimientoInventarioSerializer(movimientos, many=True)
        return JsonResponse({"movimientos": serializer.data}, status=HTTPStatus.OK)

class MovimientoInventarioCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = MovimientoInventarioSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def put(self, request, id):
        try:
            movimiento = MovimientoInventario.objects.get(id=id)
        except MovimientoInventario.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Movimiento de inventario no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )
        serializer = MovimientoInventarioSerializer(movimiento, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse(
                {"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK
            )
        return JsonResponse(
            {"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST
        )

    def delete(self, request, id):
        try:
            movimiento = MovimientoInventario.objects.get(id=id, estado=True)
            movimiento.activo = False
            movimiento.save()
            return JsonResponse(
                {"estado": "eliminado", "mensaje": "Movimiento de inventario inactivo"},
                status=HTTPStatus.OK
            )
        except MovimientoInventario.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Movimiento de inventario no encontrado"},
                status=HTTPStatus.NOT_FOUND
            )

# ==============================================================
# Lectura Código Barras
# ==============================================================
class LecturacodigobarrasGet(APIView):
    def get(self, request, id):
        try:
            lectura = Lecturacodigobarras.objects.get(id=id)
            serializer = LecturacodigobarrasSerializer(lectura)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Lecturacodigobarras.DoesNotExist:
            return JsonResponse(
                {"estado": "error", "mensaje": "Lectura de código de barras no encontrada"},
                status=HTTPStatus.NOT_FOUND
            )

class LecturacodigobarrasList(APIView):
    def get(self, request):
        lecturas = Lecturacodigobarras.objects.all().order_by("id")
        serializer = LecturacodigobarrasSerializer(lecturas, many=True)
        return JsonResponse({"lecturas": serializer.data}, status=HTTPStatus.OK)

class LecturacodigobarrasCreateUpdateDelete(APIView):    
    def post(self, request):
        serializer = LecturacodigobarrasSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)
    
    def put(self, request, id):
        try:
            lectura = Lecturacodigobarras.objects.get(id=id)
        except Lecturacodigobarras.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Lectura no encontrada"}, status=HTTPStatus.NOT_FOUND)
        serializer = LecturacodigobarrasSerializer(lectura, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)
    
    def delete(self, request, id):
        try:
            lectura = Lecturacodigobarras.objects.get(id=id)
            lectura.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "Lectura eliminada"}, status=HTTPStatus.OK)
        except Lecturacodigobarras.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Lectura no encontrada"}, status=HTTPStatus.NOT_FOUND)


# ==============================================================
# Log de Actividad
# ==============================================================
class LogactividadGet(APIView):
    def get(self, request, id):
        try:
            log = Logactividad.objects.get(id=id)
            serializer = LogactividadSerializer(log)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Logactividad.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Log de actividad no encontrado"}, status=HTTPStatus.NOT_FOUND)

class LogactividadList(APIView):
    def get(self, request):
        logs = Logactividad.objects.all().order_by("id")
        serializer = LogactividadSerializer(logs, many=True)
        return JsonResponse({"logs": serializer.data}, status=HTTPStatus.OK)

class LogactividadCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = LogactividadSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            log = Logactividad.objects.get(id=id)
        except Logactividad.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Log de actividad no encontrado"}, status=HTTPStatus.NOT_FOUND)
        serializer = LogactividadSerializer(log, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            log = Logactividad.objects.get(id=id)
            log.delete()
            return JsonResponse({"estado": "eliminado", "mensaje": "Log de actividad eliminado"}, status=HTTPStatus.OK)
        except Logactividad.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Log de actividad no encontrado"}, status=HTTPStatus.NOT_FOUND)


# ==============================================================
# Orden
# ==============================================================
class OrdenGet(APIView):
    def get(self, request, id):
        try:
            orden = Orden.objects.get(id=id)
            serializer = OrdenSerializer(orden)
            return JsonResponse({"data": serializer.data}, status=HTTPStatus.OK)
        except Orden.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Orden no encontrada"}, status=HTTPStatus.NOT_FOUND)

class OrdenList(APIView):
    def get(self, request):
        ordenes = Orden.objects.all().order_by("id")
        serializer = OrdenSerializer(ordenes, many=True)
        return JsonResponse({"ordenes": serializer.data}, status=HTTPStatus.OK)

class OrdenCreateUpdateDelete(APIView):
    def post(self, request):
        serializer = OrdenSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "creado", "data": serializer.data}, status=HTTPStatus.CREATED)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def put(self, request, id):
        try:
            orden = Orden.objects.get(id=id)
        except Orden.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Orden no encontrada"}, status=HTTPStatus.NOT_FOUND)
        serializer = OrdenSerializer(orden, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return JsonResponse({"estado": "actualizado", "data": serializer.data}, status=HTTPStatus.OK)
        return JsonResponse({"estado": "error", "mensaje": serializer.errors}, status=HTTPStatus.BAD_REQUEST)

    def delete(self, request, id):
        try:
            orden = Orden.objects.get(id=id, activo=True)
            orden.activo = False
            orden.save()
            return JsonResponse({"estado": "eliminado", "mensaje": "Orden eliminada"}, status=HTTPStatus.OK)
        except Orden.DoesNotExist:
            return JsonResponse({"estado": "error", "mensaje": "Orden no encontrada"}, status=HTTPStatus.NOT_FOUND)



# ==========
# Almacen
# ==========

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
