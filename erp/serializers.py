from rest_framework import serializers
from backend.models import Producto
from .views import *

class ProductoSerializer(serializers.ModelSerializer):

    class Meta:
        model = Producto
        fields = "__all__"

    def validate(self, data):
        campos_producto = ["nombre","descripcion","precio","codigo_barras","descuento","peso","dimensiones"]

    #Validar si los campos van vacios
        for campo in campos_producto:
            if not data.get(campo) or campo==None:
                raise serializers.ValidationError({campo:f"El campo '{campo}' no puede estar vacio"})
            
    #Validar que precio no venga vacio o sea mayor a 0

        if not data.get("precio") or data.get("precio") <= 0:
            raise serializers.ValidationError({"mensaje":"El precio tiene que ser mayor a 0"})
            
    #Validar si campo nombre existe 
        if Producto.objects.filter(nombre=data.get("nombre")).exists():
            raise serializers.ValidationError({"mensaje":"El nombre {nombre} ya existe"})
        
        return data
        
        
        
    