from django.db import models


class Reportecliente(models.Model):
    cliente = models.ForeignKey("clientes.Cliente", models.DO_NOTHING, blank=True, null=True)
    total_compras = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_pedidos = models.IntegerField()
    producto_mas_comprado = models.ForeignKey("inventario.Producto", models.DO_NOTHING, db_column='producto_mas_comprado', blank=True, null=True)

    class Meta:
        db_table = 'ReporteCliente'


class Reporteinventario(models.Model):
    fecha = models.DateField()
    producto = models.ForeignKey("inventario.Producto", models.DO_NOTHING, blank=True, null=True)
    stock_inicial = models.IntegerField()
    stock_final = models.IntegerField()
    movimientos = models.IntegerField()
    almacen = models.ForeignKey("inventario.Almacen", models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ReporteInventario'


class Reporteventa(models.Model):
    fecha = models.DateField()
    total_ventas = models.DecimalField(max_digits=12, decimal_places=2)
    total_iva = models.DecimalField(max_digits=12, decimal_places=2)
    total_descuentos = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_transacciones = models.IntegerField()
    almacen = models.ForeignKey("inventario.Almacen", models.DO_NOTHING, blank=True, null=True)

    class Meta:
        db_table = 'ReporteVenta'
