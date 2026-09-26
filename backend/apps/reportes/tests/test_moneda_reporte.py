"""Los reportes no deben sumar bolívares con dólares -- ver ``moneda_reporte``."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.configuracion.models import Moneda, TasaCambio
from apps.core.testing import BaseTenantTestCase
from apps.facturacion.models import Factura
from apps.reportes.core.moneda_reporte import monto_documento, resolver_moneda_reporte


class MonedaReporteTests(BaseTenantTestCase):
    def setUp(self):
        Moneda.objects.all().delete()
        self.ves = Moneda.objects.create(codigo="VES", nombre="Bolívar", simbolo="Bs.", es_predeterminada=True)
        self.usd = Moneda.objects.create(codigo="USD", nombre="Dólar", simbolo="$")
        hoy = timezone.localdate()
        for dias, tasa in ((10, "100"), (0, "200")):
            t = TasaCambio.objects.create(moneda=self.usd, tasa=Decimal(tasa), fuente="test")
            TasaCambio.objects.filter(pk=t.pk).update(fecha=hoy - timedelta(days=dias))
        hace_10 = timezone.now() - timedelta(days=10)
        # $10 cobrados hace 10 días a 100 Bs/$ y Bs. 1.000 cobrados ese mismo día.
        Factura.objects.create(fecha_operacion=hace_10, moneda=self.usd, tasa_cambio=Decimal("100"), total=Decimal("10"), total_base=Decimal("1000"))
        Factura.objects.create(fecha_operacion=hace_10, moneda=self.ves, tasa_cambio=Decimal("1"), total=Decimal("1000"), total_base=Decimal("1000"))

    def _sumar(self, moneda):
        return Factura.objects.aggregate(t=Sum(monto_documento(resolver_moneda_reporte(moneda))))["t"]

    def test_en_base_suma_total_base(self):
        self.assertEqual(self._sumar("base"), Decimal("2000"))

    def test_en_referencia_usa_la_tasa_del_dia_de_la_factura(self):
        # $10 + (1000 / 100) = $20 -- NO 1000/200 (tasa de hoy) ni 1010 (suma cruda).
        self.assertEqual(self._sumar("referencia").quantize(Decimal("0.01")), Decimal("20.00"))

    def test_moneda_desconocida_cae_a_base(self):
        self.assertTrue(resolver_moneda_reporte("XYZ").es_base)
