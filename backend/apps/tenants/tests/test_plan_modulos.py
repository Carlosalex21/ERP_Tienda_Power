"""Cobro por módulos: el plan decide qué endpoints exclusivos se pueden usar."""
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from apps.tenants.api.serializers import PlanSerializer
from apps.tenants.models import Plan
from apps.tenants.modulos import modulo_de_ruta


class ModuloDeRutaTests(SimpleTestCase):
    def test_ruta_exclusiva(self):
        self.assertEqual(modulo_de_ruta("/api/v1/contabilidad/reportes/libro-mayor/"), "libro_mayor")
        self.assertEqual(modulo_de_ruta("/api/v1/facturacion/libro-compra-venta/12/"), "libros_fiscales")

    def test_rutas_compartidas_y_publicas_no_se_bloquean(self):
        self.assertIsNone(modulo_de_ruta("/api/v1/inventario/productos/"))
        self.assertIsNone(modulo_de_ruta("/api/v1/crm/cotizaciones/publica/abc/"))
        self.assertIsNone(modulo_de_ruta("/api/v1/reportes/dashboard/"))


class PlanModulosTests(SimpleTestCase):
    def test_plan_sin_modulos_incluye_todo(self):
        self.assertTrue(Plan(modulos=[]).incluye_modulo("libro_mayor"))

    def test_plan_restringido(self):
        plan = Plan(modulos=["asientos_contables", "cobros"])
        self.assertTrue(plan.incluye_modulo("cobros"))
        self.assertFalse(plan.incluye_modulo("libro_mayor"))

    def test_serializer_rechaza_codigos_desconocidos(self):
        with self.assertRaises(ValidationError):
            PlanSerializer().validate_modulos(["cobros", "inventado"])
        self.assertEqual(PlanSerializer().validate_modulos(["cobros", "cobros", "nomina"]), ["cobros", "nomina"])
