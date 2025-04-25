from rest_framework import serializers
from .models import *
from .views import *
from django.utils.text import slugify
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import validate_email
# import os
# from dotenv import load_dotenv


class UserMetadataSerializer(serializers.ModelSerializer):

    def validate(self, data):
        campo_usuario = ["username","password"]

        campo_exists = ["username","email","telefono"]
        
        for campo in campo_usuario:
            if not data.get(campo) or data.get(campo)==None:
                raise serializers.ValidationError({campo:f"El campo '{campo}' no puede estar vacio"})
            
        if data.get(campo_exists).exists():
            raise serializers.ValidationError({"mensaje":f"El {campo_exists} ya existe"})
        
        return data


    
    class Meta:
        model = UserMetadata
        fields = "__all__"


# ---------------------------------------------------------------------------
# Productocategoria
# ---------------------------------------------------------------------------
class ProductocategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Productocategoria
        fields = '__all__'
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=Productocategoria.objects.all(),
                fields=['producto', 'categoria'],
                message="La relación entre este producto y categoría ya existe."
            )
        ]


# ---------------------------------------------------------------------------
# Proveedor
# ---------------------------------------------------------------------------
class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = '__all__'
    
    def validate_email(self, value):
        try:
            validate_email(value)
        except Exception:
            raise serializers.ValidationError("El email no es válido.")
        return value

    def validate_plazo_pago(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El plazo de pago no puede ser negativo.")
        return value


# ---------------------------------------------------------------------------
# Reportecliente
# ---------------------------------------------------------------------------
class ReporteclienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reportecliente
        fields = '__all__'
    
    def validate_total_compras(self, value):
        if value < 0:
            raise serializers.ValidationError("El total de compras no puede ser negativo.")
        return value

    def validate_cantidad_pedidos(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad de pedidos no puede ser negativa.")
        return value


# ---------------------------------------------------------------------------
# Reporteinventario
# ---------------------------------------------------------------------------
class ReporteinventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reporteinventario
        fields = '__all__'
    
    def validate_stock_inicial(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock inicial no puede ser negativo.")
        return value

    def validate_stock_final(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock final no puede ser negativo.")
        return value

    def validate_movimientos(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad de movimientos no puede ser negativa.")
        return value


# ---------------------------------------------------------------------------
# Reporteventa
# ---------------------------------------------------------------------------
class ReporteventaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reporteventa
        fields = '__all__'
    
    def validate_total_ventas(self, value):
        if value < 0:
            raise serializers.ValidationError("El total de ventas no puede ser negativo.")
        return value

    def validate_total_iva(self, value):
        if value < 0:
            raise serializers.ValidationError("El total de IVA no puede ser negativo.")
        return value

    def validate_total_descuentos(self, value):
        if value < 0:
            raise serializers.ValidationError("El total de descuentos no puede ser negativo.")
        return value

    def validate_cantidad_transacciones(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad de transacciones no puede ser negativa.")
        return value


# ---------------------------------------------------------------------------
# Reservastock
# ---------------------------------------------------------------------------
class ReservastockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservastock
        fields = '__all__'
    
    def validate_cantidad(self, value):
        if value < 0:
            raise serializers.ValidationError("La cantidad a reservar no puede ser negativa.")
        return value

    def validate_valido_hasta(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("La fecha 'valido_hasta' debe ser en el futuro.")
        return value


# ---------------------------------------------------------------------------
# Rol
# ---------------------------------------------------------------------------
class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = '__all__'


# ---------------------------------------------------------------------------
# Sesionusuario
# ---------------------------------------------------------------------------
class SesionusuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sesionusuario
        fields = '__all__'


# ---------------------------------------------------------------------------
# Tipodocumentofiscal
# ---------------------------------------------------------------------------
class TipodocumentofiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tipodocumentofiscal
        fields = '__all__'


# ---------------------------------------------------------------------------
# Transaccionpago
# ---------------------------------------------------------------------------
class TransaccionpagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaccionpago
        fields = '__all__'
    
    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor que cero.")
        return value

    def validate_estado(self, value):
        # Definir estados válidos según la lógica de negocio.
        allowed_states = ['exitoso', 'pendiente', 'fallido']
        if value not in allowed_states:
            raise serializers.ValidationError(
                f"El estado debe ser uno de: {', '.join(allowed_states)}."
            )
        return value


# ---------------------------------------------------------------------------
# UserMetadata
# ---------------------------------------------------------------------------
class UserMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMetadata
        fields = '__all__'
    # Se pueden incluir validaciones adicionales de campos (por ejemplo,
    # formato de avatar_url o longitud del token) según sea necesario.


# ---------------------------------------------------------------------------
# Variacionproducto
# ---------------------------------------------------------------------------
class VariacionproductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variacionproducto
        fields = '__all__'
        extra_kwargs = {
            'sku': {'required': False, 'allow_null': True}
        }
    
    def validate_stock(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value



class ConfiguracionivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuracioniva
        fields = '__all__'
    
    def validate_porcentaje_iva(self, value):
        if value < 0:
            raise serializers.ValidationError("El porcentaje de IVA debe ser positivo.")
        return value


class CupondescuentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cupondescuento
        fields = '__all__'
    
    def validate(self, data):
        # Validar que la fecha de inicio sea anterior a la fecha final.
        valido_desde = data.get('valido_desde')
        valido_hasta = data.get('valido_hasta')
        if valido_desde and valido_hasta and valido_desde > valido_hasta:
            raise serializers.ValidationError("La fecha 'valido_desde' debe ser anterior a 'valido_hasta'.")
        
        # Validar que los usos actuales no sobrepasen los usos máximos
        usos_maximos = data.get('usos_maximos')
        usos_actuales = data.get('usos_actuales')
        if usos_maximos is not None and usos_actuales is not None:
            if usos_actuales > usos_maximos:
                raise serializers.ValidationError("Los usos actuales no pueden superar los usos máximos.")
        return data


class DetallefacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Detallefactura
        fields = '__all__'
    
    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor que cero.")
        return value

    def validate_precio_unitario(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio unitario debe ser mayor que cero.")
        return value

    def validate(self, data):
        # Supongamos que el subtotal_linea debería coincidir con:
        # subtotal_linea = (cantidad * precio_unitario) - descuento (si es que hay)
        cantidad = data.get('cantidad')
        precio_unitario = data.get('precio_unitario')
        descuento = data.get('descuento') or 0  # si no se envía, se asume 0
        expected_subtotal = (cantidad * precio_unitario) - descuento
        
        subtotal_linea = data.get('subtotal_linea')
        if subtotal_linea is not None and abs(subtotal_linea - expected_subtotal) > 0.01:
            raise serializers.ValidationError(
                "El subtotal de línea no coincide con la cantidad, precio unitario y descuento."
            )
        return data


class DevolucionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Devolucion
        fields = '__all__'
    
    def validate(self, data):
        fecha_solicitud = data.get('fecha_solicitud')
        fecha_resolucion = data.get('fecha_resolucion')
        if fecha_resolucion and fecha_solicitud and fecha_resolucion < fecha_solicitud:
            raise serializers.ValidationError(
                "La fecha de resolución no puede ser anterior a la fecha de solicitud."
            )
        monto_reembolso = data.get('monto_reembolso')
        if monto_reembolso is not None and monto_reembolso < 0:
            raise serializers.ValidationError("El monto de reembolso no puede ser negativo.")
        return data


class FacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Factura
        fields = '__all__'
    
    def validate(self, data):
        subtotal = data.get('subtotal')
        descuento_total = data.get('descuento_total') or 0
        iva_total = data.get('iva_total')
        total = data.get('total')
        
        if subtotal is None or iva_total is None or total is None:
            raise serializers.ValidationError("Los campos subtotal, iva_total y total son obligatorios.")
        # Ejemplo: total = subtotal - descuento_total + iva_total
        calculated_total = subtotal - descuento_total + iva_total
        if abs(total - calculated_total) > 0.01:
            raise serializers.ValidationError(
                "La suma de subtotal - descuento_total + iva_total debe coincidir con el total."
            )
        return data


class FacturaelectronicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facturaelectronica
        fields = '__all__'
    
    def validate_csv(self, value):
        # Validamos que el nombre del archivo termine en .csv
        if not value.endswith('.csv'):
            raise serializers.ValidationError("El campo csv debe ser un archivo con extensión .csv.")
        return value


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventario
        fields = '__all__'
    
    def validate_stock_minimo(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("El stock mínimo no puede ser negativo.")
        return value
    
    def validate_tipo_movimiento(self, value):
        valid_types = ['entrada', 'salida']
        if value not in valid_types:
            raise serializers.ValidationError("Tipo de movimiento inválido.")
        return value


class LecturacodigobarrasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lecturacodigobarras
        fields = '__all__'
    
    def validate_codigo_barras(self, value):
        if not value.strip():
            raise serializers.ValidationError("El código de barras no puede estar vacío.")
        return value
    
    def validate_fecha_lectura(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError(
                "La fecha de lectura no puede ser en el futuro."
            )
        return value


class LogactividadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Logactividad
        fields = '__all__'
    
    def validate_accion(self, value):
        if not value:
            raise serializers.ValidationError("La acción debe ser especificada.")
        return value


class OrdenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Orden
        fields = '__all__'
    
    def validate_estado(self, value):
        # Ejemplo: se definen estados permitidos.
        allowed_estados = ["abierta", "cerrada", "pagada"]
        if value not in allowed_estados:
            raise serializers.ValidationError("Estado no válido.")
        return value
    
    def validate_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("El total debe ser mayor que cero.")
        return value




class ProductoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Producto
        fields = "__all__"
        depth=1

    def validate_cantidad(self, value):
        if value < 0:
             raise serializers.ValidationError("La cantidad del producto no puede ser negativa.")
        return value
    
    def validate_categoria(self, value):
        if not value:
            raise serializers.ValidationError("El producto debe estar asociado a una categoria valida")
        return value
    
    def validate_almacen(self,value):
        if not value:
            raise serializers.ValidationError("El producto debe estar asociado a un almacen valido")
        return value

    def validate(self, data):
        campos_producto = ["nombre","descripcion","precio","cantidad","categoria","codigo_barras","almacen","peso"]

    #Validar si los campos van vacios
        for campo in campos_producto:
            if not data.get(campo) or data.get(campo)==None:
                raise serializers.ValidationError({campo:f"El campo '{campo}' no puede estar vacio"})
            
    #Validar que precio no venga vacio o sea mayor a 0

        if not data.get("precio") or data.get("precio") <= 0:
            raise serializers.ValidationError({"mensaje":"El precio tiene que ser mayor a 0"})
        
            
    #Validar si campo nombre existe 
        if Producto.objects.filter(nombre=data.get("nombre")).exists():
            raise serializers.ValidationError({"mensaje":"El nombre ya existe"})
        
        return data


class AlmacenSerializer(serializers.ModelSerializer):

    def validate(self,data):

        campo_almacen = ["nombre", "direccion", "telefono"]

        for campo in campo_almacen:
            if not data.get(campo) or data.get(campo)==None:
                raise serializers.ValidationError({"mensaje":f"El campo {campo} no puede ir vacio"})
            
        if Almacen.objects.filter(nombre=data.get("nombre")).exists():
            raise serializers.ValidationError({"mensaje":f"El nombre ya existe"})
        
        return data
        
    
    class Meta:
        model = Almacen
        fields = "__all__"

class InventarioSerializer(serializers.ModelSerializer):
    
    # producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    # almacen_nombre = serializers.CharField(source="almacen.nombre", read_only=True)

    def validate_producto(self, value):
        if not value.activo:
            raise serializers.ValidationError("No puedes agregar productos inactivos al inventario.")
        return value

    def validate_almacen(self, value):
        if not value:
            raise serializers.ValidationError("El inventario debe estar asociado a un almacén válido.")
        return value
    
    # def validate(self, data):
    #     """ Validar que la cantidad sea al menos igual al stock mínimo """
    #     cantidad = data.get("cantidad", 0)
    #     stock_minimo = data.get("stock_minimo", 0)

    #     if cantidad < stock_minimo:
    #          raise serializers.ValidationError("La cantidad disponible no puede ser menor que el stock mínimo.")

    #     return data
    
    class Meta:
        model = Inventario
        fields = "__all__"
        depth=1  #Esto hará que los `ForeignKey` se expandan en la respuesta JSON




class CategoriaSerializer(serializers.ModelSerializer):

    def validate_padre(self, value):

        if self.instance and self.instance.id == value.id:
            raise serializers.ValidationError("Una categoría no puede ser su propio padre")

        return value
    
    
    def validate_activo(self, value):
        if not value and Categoriaproducto.objects.filter(padre=self.instance).exists():
            raise serializers.ValidationError("No puedes desactivar una categoría con subcategorías activas.")

        return value
    

    def update(self, instance, validated_data):
        nuevo_nombre = validated_data.get("nombre", instance.nombre)
        if nuevo_nombre != instance.nombre:
            validated_data["slug"] = slugify(nuevo_nombre)

        return super().update(instance, validated_data)
    

    def validate_nombre(self, value):
        return value.strip()

    
    def validate(self, data):
        padre = data.get("padre")
        
        if padre:
            ancestro = padre
            while ancestro:
                if ancestro == self.instance:
                    raise serializers.ValidationError("No se puede crear una estructura cíclica.")
                ancestro = ancestro.padre

        profundidad_maxima = 5  
        nivel_actual = 0
        
        while padre:
            nivel_actual += 1
            if nivel_actual > profundidad_maxima:
                raise serializers.ValidationError(f"No puedes crear más de {profundidad_maxima} niveles de subcategoría.")
            padre = padre.padre

        if not data.get("nombre") or data.get("nombre")==None:
            raise serializers.ValidationError("El campo nombre no puede estar vacio")
        
        if Categoriaproducto.objects.filter(nombre=data.get("nombre")).exists():
            raise serializers.ValidationError("El nombre ya existe")
        
        if padre and not isinstance(padre, Categoriaproducto):
            raise serializers.ValidationError("El padre debe ser una categoría válida.")
        
        return data


    class Meta:
        model = Categoriaproducto
        fields = "__all__"



class ClienteSerializer(serializers.ModelSerializer):
	      
    def validate(self, data):

        campo_cliente = ["tipo_documento","documento","nombre","email","telefono","direccion"]

        for campo in campo_cliente:
             if not data.get(campo) or data.get(campo)==None:
                  raise serializers.ValidationError({campo:f"El campo '{campo}' no puede estar vacio"})
             
        #Validaciones si existe el registro al mandar metodo post
        if Cliente.objects.filter(documento=data.get("documento")).exists():
            raise serializers.ValidationError({"mensaje":f"El documento ya existe"})
        if Cliente.objects.filter(documento=data.get("nombre")).exists():
            raise serializers.ValidationError({"mensaje":f"El nombre ya existe"})    
        if Cliente.objects.filter(nombre=data.get("email")).exists():
            raise serializers.ValidationError({"mensaje":f"El email ya existe"}) 
        
        tipo_documento = {
            "DNI":"Documento Nacional de Identidad",
            "NIE":"Extranjeros",
            "P":"Pasaporte"
        }

        if data.get("tipo_documento") not in tipo_documento.keys():
            raise serializers.ValidationError({"mensaje":"El tipo de documento no es valido"})

        return data
    class Meta:
        model = Cliente
        fields = "__all__"
        
        
    