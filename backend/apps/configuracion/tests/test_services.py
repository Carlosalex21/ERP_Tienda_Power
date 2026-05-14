from django_tenants.test.cases import TenantTestCase
from ..models import ConfiguracionCorrelativo
from ..core.config_service import obtener_y_actualizar_correlativo

class ConfigServiceTests(TenantTestCase):

    def test_obtener_y_actualizar_correlativo_primera_vez(self):
        """Prueba que el primer correlativo se genere correctamente."""
        correlativo = obtener_y_actualizar_correlativo()
        self.assertEqual(correlativo, "F-001")
        config = ConfiguracionCorrelativo.objects.get(pk=1)
        self.assertEqual(config.current_number, 1)

    def test_obtener_y_actualizar_correlativo_multiples_veces(self):
        """Prueba que los correlativos se incrementen correctamente."""
        obtener_y_actualizar_correlativo() # Llama 1
        obtener_y_actualizar_correlativo() # Llama 2
        correlativo_3 = obtener_y_actualizar_correlativo() # Llama 3
        self.assertEqual(correlativo_3, "F-003")
        config = ConfiguracionCorrelativo.objects.get(pk=1)
        self.assertEqual(config.current_number, 3)
