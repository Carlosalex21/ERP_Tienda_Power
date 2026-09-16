from decimal import Decimal
from unittest.mock import patch, Mock

import requests

from apps.core.testing import BaseTenantTestCase as TenantTestCase
from ..models import ConfiguracionEmpresa, Moneda, TasaCambio
from ..services import bcv_service
from ..services.bcv_service import asegurar_tasa_bcv_del_dia, BcvApiError


def _mock_response(promedio=832.4883, status_ok=True):
    resp = Mock()
    resp.json.return_value = {"promedio": promedio}
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.HTTPError("boom")
    return resp


class BcvServiceTests(TenantTestCase):

    def setUp(self):
        ConfiguracionEmpresa.objects.update_or_create(pk=1, defaults={"pais_codigo": "VE"})
        self.ves = Moneda.objects.create(codigo="VES", nombre="Bolívar", es_predeterminada=True)
        self.usd = Moneda.objects.create(codigo="USD", nombre="Dólar", es_predeterminada=False)
        # El guard en memoria es compartido entre tests (módulo importado una
        # sola vez) -- se limpia para que cada test arranque sin rastro del anterior.
        bcv_service._ultima_verificacion.clear()

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_crea_tasa_bcv_si_no_existe_hoy(self, mock_get):
        mock_get.return_value = _mock_response(promedio=832.4883)

        tasa = asegurar_tasa_bcv_del_dia()

        self.assertIsNotNone(tasa)
        self.assertEqual(tasa.moneda, self.usd)
        self.assertEqual(tasa.tasa, Decimal("832.4883"))
        self.assertEqual(tasa.fuente, bcv_service.FUENTE_BCV)
        mock_get.assert_called_once()

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_no_pisa_tasa_manual_ya_cargada_hoy(self, mock_get):
        TasaCambio.objects.create(moneda=self.usd, tasa=Decimal("900"), fuente="Manual")

        resultado = asegurar_tasa_bcv_del_dia()

        self.assertIsNone(resultado)
        mock_get.assert_not_called()
        self.assertEqual(TasaCambio.objects.filter(moneda=self.usd).count(), 1)

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_solo_consulta_la_api_una_vez_por_dia_aunque_se_llame_varias_veces(self, mock_get):
        mock_get.return_value = _mock_response(promedio=832.4883)

        asegurar_tasa_bcv_del_dia()
        asegurar_tasa_bcv_del_dia()
        asegurar_tasa_bcv_del_dia()

        mock_get.assert_called_once()
        self.assertEqual(TasaCambio.objects.filter(moneda=self.usd).count(), 1)

    @patch("apps.configuracion.services.bcv_service.obtener_pais_tenant", return_value="CO")
    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_no_aplica_a_tenants_fuera_de_venezuela(self, mock_get, mock_pais):
        resultado = asegurar_tasa_bcv_del_dia()

        self.assertIsNone(resultado)
        mock_get.assert_not_called()

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_api_caida_no_rompe_y_no_crea_tasa(self, mock_get):
        mock_get.return_value = _mock_response(status_ok=False)

        resultado = asegurar_tasa_bcv_del_dia()

        self.assertIsNone(resultado)
        self.assertEqual(TasaCambio.objects.filter(moneda=self.usd).count(), 0)

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_forzar_pisa_tasa_de_hoy_y_propaga_error_de_api(self, mock_get):
        TasaCambio.objects.create(moneda=self.usd, tasa=Decimal("900"), fuente="Manual")
        mock_get.return_value = _mock_response(status_ok=False)

        with self.assertRaises(BcvApiError):
            asegurar_tasa_bcv_del_dia(forzar=True)

    @patch("apps.configuracion.services.bcv_service.requests.get")
    def test_forzar_crea_tasa_nueva_aunque_ya_haya_una_de_hoy(self, mock_get):
        TasaCambio.objects.create(moneda=self.usd, tasa=Decimal("900"), fuente="Manual")
        mock_get.return_value = _mock_response(promedio=850.0)

        tasa = asegurar_tasa_bcv_del_dia(forzar=True)

        self.assertIsNotNone(tasa)
        self.assertEqual(tasa.tasa, Decimal("850.0"))
        self.assertEqual(TasaCambio.objects.filter(moneda=self.usd).count(), 2)
