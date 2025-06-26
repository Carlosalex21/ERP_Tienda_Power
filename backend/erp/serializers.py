from rest_framework import serializers
from .models import *
from .views import *
from django.db.models import Sum
from django.utils.text import slugify
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import validate_email
import json
from django.contrib.auth import get_user_model
# import os
# from dotenv import load_dotenv

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token

    def validate(self, attrs):
        login = attrs.get("username") 
        password = attrs.get("password")
        UserModel = get_user_model()
        user = None

        # Buscar por username
        try:
            user = UserModel.objects.get(username=login)
        except UserModel.DoesNotExist:
            # Buscar por email
            try:
                user = UserModel.objects.get(email=login)
            except UserModel.DoesNotExist:
                raise self.fail('no_active_account')

        # Autenticar
        if user and user.check_password(password) and user.is_active:
            data = super().validate({"username": user.username, "password": password})
            # Obtener el rol desde UserMetaData
            user_metadata = getattr(user, 'metadata', None)
            if user_metadata and user_metadata.rol:
                data['role'] = user_metadata.rol.nombre
            else:
                data['role'] = None

                data['nombre_usuario'] = (
                user_metadata.nombre
                if user_metadata and getattr(user_metadata, 'nombre', None)
                else user.first_name or user.username
            )
            return data
        else:
            raise self.fail('no_active_account')


class UserMetadataSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    rol = serializers.CharField(source="rol.nombre", read_only=True)
    tipo_documento = serializers.PrimaryKeyRelatedField(queryset=Tipodocumentofiscal.objects.all(), allow_null=True, required=False)

    class Meta:
        model = UserMetadata
        fields = '__all__'
        read_only_fields = ['fecha_creacion', 'fecha_modificacion']


class UserMetadataCreateSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    correo = serializers.EmailField(write_only=True)
    rol = serializers.PrimaryKeyRelatedField(queryset=Rol.objects.all(), required=False, allow_null=True)
    tipo_documento = serializers.PrimaryKeyRelatedField(queryset=Tipodocumentofiscal.objects.all(), required=False, allow_null=True)

    class Meta:
        model = UserMetadata
        fields = [
            'usuario', 'password', 'correo', 'rol', 'telefono', 'direccion',
            'nombre', 'apellido', 'tipo_documento', 'numero_documento'
        ]

    def validate_usuario(self, value):
        # Checa si el username ya existe
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ese nombre de usuario ya está en uso.")
        return value

    def create(self, validated_data):
        username = validated_data.pop('usuario')
        password = validated_data.pop('password')
        email = validated_data.pop('correo')

        # Garantiza unicidad de username (opcional, si quieres auto-incrementar)
        original_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1

        user = User.objects.create_user(username=username, email=email, password=password)
        validated_data['user'] = user
        validated_data['correo'] = email
        validated_data['verificado'] = True
        # El campo correo puede o no ir en metadatos según tu modelo
        return UserMetadata.objects.create(**validated_data)

class ConfiguracionCorrelativoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionCorrelativo
        fields = ['prefijo', 'current_number', 'number_length']



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
        depth = 1

class ReporteinventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reporteinventario
        fields = '__all__'
        depth = 1

class ReporteventaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reporteventa
        fields = '__all__'
        depth = 1


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


# =============
# Metodo Pago

class MetodoPagoSerializer(serializers.ModelSerializer):

    def validate(self, data):
    # Lista de opciones permitidas para "tipo_metodo":
        opciones_permitidas = ["Bizum", "Tarjeta", "Efectivo", "Pagar luego"]

        # Validar que el campo tipo_metodo esté entre las opciones permitidas.
        tipo = data.get("tipo_metodo")
        if tipo not in opciones_permitidas:
            raise serializers.ValidationError(
                {"tipo_metodo": f"El tipo de método debe ser una de las siguientes opciones: {', '.join(opciones_permitidas)}."}
            )
        
        if tipo == "Pagar luego":
            data["monto_recibido"] = 0

        # Los campos requeridos:
        campos = ["nombre", "tipo_metodo"]
        for campo in campos:
            if not data.get(campo):
                raise serializers.ValidationError({campo: f"El campo {campo} no puede estar vacío."})
        
        return data


    class Meta:
        model = MetodoPago
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
# tdf es tipo de documento fiscal ---------------------------------------------------------------------------
class UserMetadataSerializer(serializers.ModelSerializer):
    rol = RolSerializer(read_only=True)
    tipo_documento = TipodocumentofiscalSerializer(read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    class Meta:
        model = UserMetadata
        fields = '__all__'


class ValorAtributoSimpleSerializer(serializers.Serializer):
    valor = serializers.CharField()

class AtributoCrearConValoresSerializer(serializers.ModelSerializer):
    valores = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )

    class Meta:
        model = Atributo
        fields = ['id', 'nombre', 'valores']

    def create(self, validated_data):
        valores = validated_data.pop('valores', [])
        atributo = Atributo.objects.create(**validated_data)
        for valor in valores:
            ValorAtributo.objects.create(atributo=atributo, valor=valor)
        return atributo

class AtributoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Atributo
        fields = ['id', 'nombre']

class ValorAtributoSerializer(serializers.ModelSerializer):
    atributo = AtributoSerializer(read_only=True)
    atributo_id = serializers.PrimaryKeyRelatedField(queryset=Atributo.objects.all(), source='atributo', write_only=True)
    class Meta:
        model = ValorAtributo
        fields = ['id', 'atributo', 'atributo_id', 'valor']

class VariacionproductoSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    atributos = ValorAtributoSerializer(many=True, read_only=True)
    atributos_id = serializers.PrimaryKeyRelatedField(
        queryset=ValorAtributo.objects.all(), source='atributos', many=True, write_only=True, required=False
    )
    imagen = serializers.ImageField(use_url=True, required=False, allow_null=True)

    class Meta:
        model = Variacionproducto
        fields = [
            'id', 'producto', 'nombre','atributos', 'atributos_id', 'sku',
            'precio', 'cantidad', 'codigo_barras', 'imagen'
        ]
        extra_kwargs = {
            'sku': {'required': False, 'allow_null': True},
            'precio': {'allow_null': True},
            'cantidad': {'allow_null': True},
            'codigo_barras': {'allow_null': True},
            'imagen': {'allow_null': True},
            'producto': {'required': True},
            'nombre': {'required': False, 'allow_blank': True, 'allow_null': True}
        }

    def get_total_stock(self, obj):
        qs = Variacionproducto.objects.filter(nombre=obj.nombre)
        result = qs.aggregate(total=Sum('cantidad'))
        return result['total'] or 0


    def validate(self, data):
        nombre = data.get("nombre")
        producto = data.get("producto") or getattr(self.instance, "producto", None)
        if not self.instance:
            if nombre and producto and Variacionproducto.objects.filter(nombre=nombre, producto=producto).exists():
                raise serializers.ValidationError({
                    "nombre": "Ya existe una variante con este nombre para este producto."
                })
        else:
            nuevo_nombre = data.get("nombre", self.instance.nombre)
            if nuevo_nombre != self.instance.nombre:
                if Variacionproducto.objects.filter(nombre=nuevo_nombre, producto=producto).exclude(id=self.instance.id).exists():
                    raise serializers.ValidationError({
                        "nombre": "Ya existe una variante con este nombre para este producto."
                    })

        if "precio" in data and data["precio"] is not None and data["precio"] < 0:
            raise serializers.ValidationError({"precio": "El precio no puede ser negativo."})

        if "cantidad" in data and data["cantidad"] is not None and data["cantidad"] < 0:
            raise serializers.ValidationError({"cantidad": "La cantidad no puede ser negativa."})

        sku = data.get("sku")
        if sku:
            qs = Variacionproducto.objects.filter(sku=sku)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({"sku": "El SKU ya existe en otra variante."})

        codigo_barras = data.get("codigo_barras")
        if codigo_barras:
            qs = Variacionproducto.objects.filter(codigo_barras=codigo_barras)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({"codigo_barras": "El código de barras ya existe en otra variante."})

        return data

    def validate_nombre(self, value):
        if value is None:
            return ""
        return value.strip()

    def create(self, validated_data):
        atributos = validated_data.pop('atributos', [])
        if not validated_data.get('nombre'):
            validated_data['nombre'] = 'Variante'
        if not validated_data.get('sku'):
            validated_data['sku'] = slugify(validated_data['nombre'])
        variacion = Variacionproducto.objects.create(**validated_data)
        if atributos:
            variacion.atributos.set(atributos)
        return variacion

    def update(self, instance, validated_data):
        atributos = validated_data.pop('atributos', None)
        nombre = validated_data.get('nombre')
        if (not nombre or nombre.strip() == "") and atributos:
            valores = [v.valor for v in atributos]
            validated_data['nombre'] = f"{instance.producto.nombre} {' '.join(valores)}"
        if not validated_data.get("sku"):
            validated_data["sku"] = slugify(validated_data['nombre'])
        instance = super().update(instance, validated_data)
        if atributos is not None:
            instance.atributos.set(atributos)
        return instance


class ConfiguracionivaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Configuracioniva
        fields = '__all__'
    
    def validate_porcentaje_iva(self, value):
        if value <= 0:
            raise serializers.ValidationError("El porcentaje de IVA debe ser positivo.")
        return value
    
    def validate_nombre(self, value):
        if not value or value.strip() == "":
            raise serializers.ValidationError("El campo no puede estar vacío.")
        if Configuracioniva.objects.filter(nombre=value).exists():
            raise serializers.ValidationError("El nombre ya existe.")
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


#Reportes Serializer
class FacturaReporteSerializer(serializers.ModelSerializer):
    """
    Serializer para mostrar una lista detallada de facturas, incluyendo
    el nombre del cliente en lugar de solo su ID.
    """
    # Usamos StringRelatedField para obtener el 'nombre' del cliente directamente.
    cliente = serializers.StringRelatedField()
    almacen = serializers.StringRelatedField()
    metodo_pago = serializers.StringRelatedField()

    class Meta:
        model = Factura
        # Define los campos que quieres ver en tu tabla de reporte detallado
        fields = [
            'id',
            'correlativo',
            'fecha_operacion',
            'cliente',
            'estado',
            'subtotal',
            'descuento_global',
            'iva_total',
            'total',
            'metodo_pago',
            'almacen',
        ]

class DetalleFacturaReporteSerializer(serializers.ModelSerializer):
    """Serializer para los productos dentro de una factura."""
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    variante_nombre = serializers.CharField(source='variante.nombre', default='', read_only=True)

    class Meta:
        model = Detallefactura
        fields = ['producto_nombre', 'variante_nombre', 'cantidad', 'precio_unitario', 'descuento', 'total_linea']

class FacturaDetalladaReporteSerializer(serializers.ModelSerializer):
    """
    Serializer principal para el reporte detallado, que anida
    la información del cliente, empleado y los detalles (productos).
    """
    cliente = serializers.StringRelatedField()
    metodo_pago = serializers.StringRelatedField()
    creado_por = serializers.StringRelatedField(source='creado_por.user.username', default='N/A')
    detalles = DetalleFacturaReporteSerializer(source='detallefactura_set', many=True, read_only=True)

    class Meta:
        model = Factura
        fields = [
            'id', 'correlativo', 'fecha_operacion', 'cliente', 'creado_por',
            'estado', 'subtotal', 'descuento_global', 'iva_total', 'total',
            'metodo_pago', 'detalles'
        ]


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
        descuento_global = data.get('descuento_global') or 0
        iva_total = data.get('iva_total')
        total = data.get('total')
        metodo_pago = data.get('metodo_pago')
        
        if subtotal is None or iva_total is None or total is None:
            raise serializers.ValidationError("Los campos subtotal, iva_total y total son obligatorios.")
        # Ejemplo: total = subtotal - descuento_total + iva_total
        calculated_total = subtotal - descuento_global + iva_total
        if abs(total - calculated_total) > 0.01:
            raise serializers.ValidationError(
                "La suma de subtotal - descuento + iva_total debe coincidir con el total."
            )
        
        if metodo_pago and metodo_pago.tipo_metodo == "Pagar luego" and total > 0:
            data["estado"] = "pendiente"

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
        allowed_estados = ["abierta", "cerrada", "pagada", "pendiente"]
        if value not in allowed_estados:
            raise serializers.ValidationError("Estado no válido.")
        return value
    
    def validate_total(self, value):
        if value <= 0:
            raise serializers.ValidationError("El total debe ser mayor que cero.")
        return value
    



class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    almacen_nombre = serializers.CharField(source="almacen.nombre", read_only=True)
    imagen = serializers.ImageField(use_url=True, required=False, allow_null=True)
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoriaproducto.objects.all())
    almacen = serializers.PrimaryKeyRelatedField(queryset=Almacen.objects.all())
    configuracion_iva = serializers.PrimaryKeyRelatedField(queryset=Configuracioniva.objects.all())
    precio_con_iva = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Producto
        fields = "__all__"
        extra_kwargs = {
            'precio': {'required': False, 'allow_null': True},
            'cantidad': {'required': False, 'allow_null': True},
            'codigo_barras': {'required': False, 'allow_blank': True, 'allow_null': True},
            'slug': {'read_only': True, 'required': False},
        }

    def validate_cantidad(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("La cantidad del producto no puede ser negativa.")
        return value

    def create(self, validated_data):
        # LÓGICA ORIGINAL: SOLO UNA VARIANTE PARA PRODUCTO VARIABLE
        variantes_data_raw = self.initial_data.get('variantes', None)

        print(f"--- DEBUG: ProductoSerializer.create ---")
        print(f"Raw variantes_data_raw: {variantes_data_raw} (tipo: {type(variantes_data_raw)})")

        # Crear el producto principal primero
        validated_data.pop('variantes', None)
        producto = Producto.objects.create(**validated_data)
        request = self.context.get("request")

        if validated_data.get('tipo') == 'variable':
            # Solo admite UNA variante por producto variable
            if variantes_data_raw:
                import json
                if isinstance(variantes_data_raw, str):
                    variantes_data_list = json.loads(variantes_data_raw)
                elif isinstance(variantes_data_raw, list):
                    variantes_data_list = variantes_data_raw
                else:
                    variantes_data_list = []

                if variantes_data_list:
                    # Tomamos SOLO la primera variante del array
                    variante_dict = variantes_data_list[0]
                    serializer_data = {
                        'producto': producto.id,
                        'atributos_id': [variante_dict.get('atributos_id', [None])[0]],
                        'sku': variante_dict.get('sku'),
                        'precio': variante_dict.get('precio'),
                        'cantidad': variante_dict.get('cantidad'),
                        'codigo_barras': variante_dict.get('codigo_barras'),
                        'nombre': variante_dict.get('nombre'),
                    }

                    if request and hasattr(request, 'FILES'):
                        if 'variantes[0][imagen]' in request.FILES:
                            serializer_data['imagen'] = request.FILES['variantes[0][imagen]']

                    print('serializer_data:', serializer_data)
                    
                    serializer_variante = VariacionproductoSerializer(data=serializer_data, context=self.context)
                    serializer_variante.is_valid(raise_exception=True)
                    serializer_variante.save()
        producto.refresh_from_db()
        return producto

    def update(self, instance, validated_data):
        validated_data.pop('variantes', None)
        nuevo_nombre = validated_data.get("nombre", instance.nombre)
        if nuevo_nombre != instance.nombre:
            nuevo_slug = slugify(nuevo_nombre)
            if Producto.objects.filter(slug=nuevo_slug).exclude(id=instance.id).exists():
                raise serializers.ValidationError({"slug": "Ya existe un producto con este slug."})
            validated_data["slug"] = nuevo_slug

        imagen = validated_data.get("imagen", None)
        if not imagen:
            validated_data["imagen"] = instance.imagen

        validated_data["descuento"] = validated_data.get("descuento", instance.descuento)
        instance = super().update(instance, validated_data)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        variantes_qs = instance.variacionproducto_set.all()
        data['variantes'] = VariacionproductoSerializer(variantes_qs, many=True, context=self.context).data
        return data

    def validate_nombre(self, value):
        if value is None:
            return ""
        return value.strip()

    def validate_categoria(self, value):
        if not value:
            raise serializers.ValidationError("El producto debe estar asociado a una categoría válida.")
        return value

    def validate_almacen(self, value):
        if not value:
            raise serializers.ValidationError("El producto debe estar asociado a un almacén válido.")
        return value

    def validate(self, data):
        tipo = data.get("tipo", getattr(self.instance, "tipo", None))
        is_creating = not self.instance

        required_fields_general = ["nombre", "descripcion", "categoria", "almacen", "peso"]
        for campo in required_fields_general:
            if (is_creating and not data.get(campo)) or \
               (campo in data and not data.get(campo) and data.get(campo) is not None and data.get(campo) != ""):
                if not (campo == "nombre" and not is_creating and campo not in data):
                    raise serializers.ValidationError({campo: f"El campo '{campo}' no puede estar vacío."})

        if "descuento" in data:
            if data["descuento"] in [None, ""]:
                data["descuento"] = 0.0
            else:
                try:
                    descuento_val = float(data["descuento"])
                    if descuento_val < 0:
                        raise serializers.ValidationError({"descuento": "El descuento no puede ser negativo."})
                    data["descuento"] = descuento_val
                except (ValueError, TypeError):
                    raise serializers.ValidationError({"descuento": "Se requiere un número válido para el descuento."})

        if tipo == "simple":
            if data.get("precio") is None or data.get("precio") <= 0:
                raise serializers.ValidationError({"precio": "Para producto simple, el precio debe ser mayor a 0."})
            if data.get("cantidad") is None or data.get("cantidad") < 0:
                raise serializers.ValidationError({"cantidad": "Para producto simple, la cantidad debe ser un número mayor o igual a 0."})
            if not data.get("codigo_barras"):
                raise serializers.ValidationError({"codigo_barras": "El código de barras es obligatorio para producto simple."})

            if is_creating and not data.get("imagen"):
                 raise serializers.ValidationError({"imagen": "Debe subir una imagen para el producto simple."})

        elif tipo == "variable":
            data['precio'] = None
            data['cantidad'] = None
            data['codigo_barras'] = None
            variantes_presentes = 'variantes' in self.initial_data
            if not variantes_presentes:
                raise serializers.ValidationError({"variantes": "Para un producto variable, debe agregar al menos una variante."})

        elif tipo is None and is_creating:
             raise serializers.ValidationError({"tipo": "Debe especificar el tipo de producto (simple o variable)."})

        return data



class AlmacenSerializer(serializers.ModelSerializer):

    def validate(self,data):

        campo_almacen = ["nombre", "direccion", "telefono", "estado"]

        for campo in campo_almacen:
            if not data.get(campo) or data.get(campo)==None:
                raise serializers.ValidationError({"mensaje":f"El campo {campo} no puede ir vacio"})
            
        if not self.instance:
            # En creación, se verifica que el nombre sea único
            if Almacen.objects.filter(nombre=data.get("nombre")).exists():
                raise serializers.ValidationError({
                    "mensaje": "El nombre ya existe"
                })
        else:
            # En actualización:
            # Si el nombre se está modificando, se verifica que el nuevo nombre no exista en otro registro
            nuevo_nombre = data.get("nombre", self.instance.nombre)
            if nuevo_nombre != self.instance.nombre:
                if Almacen.objects.filter(nombre=nuevo_nombre).exclude(id=self.instance.id).exists():
                    raise serializers.ValidationError({
                        "mensaje": "El nombre ya existe"})
        
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

     # Agregamos un campo que obtiene el nombre del padre usando un método
    padre_nombre = serializers.SerializerMethodField(read_only=True)
    # Agregamos el campo 'padre' para las operaciones de escritura (crear/actualizar).
    padre = serializers.PrimaryKeyRelatedField(
        queryset=Categoriaproducto.objects.all(), 
        allow_null=True, 
        required=False
    )

    def get_padre_nombre(self, obj):
        # Si existe un padre, devolvemos solamente su nombre; de lo contrario, retornamos un guión o None
        return obj.padre.nombre if obj.padre else "-"

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
        
        if self.instance:
            if Categoriaproducto.objects.filter(nombre=data.get("nombre")).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("El nombre ya existe")
        else:
            if Categoriaproducto.objects.filter(nombre=data.get("nombre")).exists():
                raise serializers.ValidationError("El nombre ya existe")
        
        if padre and not isinstance(padre, Categoriaproducto):
            raise serializers.ValidationError("El padre debe ser una categoría válida.")
        
        return data


    class Meta:
        model = Categoriaproducto
        fields = ['id', 'nombre', 'slug', 'activo', 'padre', 'padre_nombre']



class ClienteSerializer(serializers.ModelSerializer):
	      
    def validate(self, data):

        campo_cliente = ["tipo_documento","documento","nombre","email","telefono","direccion"]

        for campo in campo_cliente:
             if not data.get(campo) or data.get(campo)==None:
                  raise serializers.ValidationError({campo:f"El campo '{campo}' no puede estar vacio"})
             
        #Validaciones si existe el registro al mandar metodo post
        if Cliente.objects.filter(documento=data.get("documento")).exists():
            raise serializers.ValidationError({"mensaje":f"El documento ya existe"})
        if Cliente.objects.filter(nombre=data.get("nombre")).exists():
            raise serializers.ValidationError({"mensaje":f"El nombre ya existe"})    
        if Cliente.objects.filter(email=data.get("email")).exists():
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
        
        
    