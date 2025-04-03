from rest_framework import serializers
from .models import *
from .views import *
from django.utils.text import slugify

class ProductoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Producto
        fields = "__all__"

    def validate(self, data):
        campos_producto = ["nombre","descripcion","precio","codigo_barras","descuento","peso","dimensiones"]

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
        
        
    