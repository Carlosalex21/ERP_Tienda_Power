from django.db import models
from django.utils import timezone


class LoteProducto(models.Model):
    """
    Lote de un producto con su fecha de vencimiento -- informativo/de
    trazabilidad a propósito: NO reemplaza `Producto.cantidad` (que sigue
    siendo la fuente de verdad para el POS/catálogo/predicción de stock ya
    existentes). Un producto puede tener varios lotes con vencimientos
    distintos; sumar `cantidad` de sus lotes activos es responsabilidad de
    quien lo registra, no algo que el sistema reconcilia solo todavía (v1:
    alertar de vencimientos próximos, no descuento automático FEFO al vender).
    """

    producto = models.ForeignKey('inventario.Producto', on_delete=models.CASCADE, related_name='lotes')
    numero_lote = models.CharField(max_length=50, blank=True, null=True)
    fecha_vencimiento = models.DateField()
    cantidad = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'LoteProducto'
        ordering = ['fecha_vencimiento']

    def __str__(self) -> str:
        return f"{self.producto.nombre} -- lote {self.numero_lote or 's/n'} ({self.fecha_vencimiento})"

    @property
    def dias_para_vencer(self) -> int:
        return (self.fecha_vencimiento - timezone.now().date()).days

    @property
    def vencido(self) -> bool:
        return self.dias_para_vencer < 0
