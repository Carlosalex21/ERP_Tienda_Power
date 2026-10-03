from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.configuracion.models import ConfiguracionEmpresa, Moneda, TasaCambio
from apps.core.testing import BaseTenantTestCase
from apps.inmuebles.models import Edificio, Unidad

User = get_user_model()

TASA = Decimal('40.00')


class InmueblesBase(BaseTenantTestCase):
    """Tenant de prueba con moneda base VES, USD con tasa 40 y un edificio de 3 unidades."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.user = User.objects.create_user(username='admin_inm', password='x')
        ConfiguracionEmpresa.objects.get_or_create(pk=1, defaults={'nombre_comercial': 'Administradora Prueba'})
        ves, _ = Moneda.objects.get_or_create(codigo='VES', defaults={'nombre': 'Bolívar', 'simbolo': 'Bs.', 'es_predeterminada': True})
        usd, _ = Moneda.objects.get_or_create(codigo='USD', defaults={'nombre': 'Dólar', 'simbolo': '$', 'es_predeterminada': False})
        TasaCambio.objects.create(moneda=usd, tasa=TASA, activa=True)

        self.edificio = Edificio.objects.create(
            nombre='Residencias El Parque', dia_vencimiento=5, mora_pct_mensual=Decimal('2.00'), dias_gracia=0,
            fondo_reserva_pct=Decimal('10.00'),
        )
        self.ana = Cliente.objects.create(nombre='Ana Pérez', documento='V-1', telefono='0414-0000001')
        self.luis = Cliente.objects.create(nombre='Luis Soto', documento='V-2', telefono='0414-0000002')
        self.eva = Cliente.objects.create(nombre='Eva Ruiz', documento='V-3', telefono='0414-0000003')
        self.u1 = self.unidad('A-1', Decimal('50.0000'), self.ana)
        self.u2 = self.unidad('A-2', Decimal('30.0000'), self.luis)
        self.u3 = self.unidad('A-3', Decimal('20.0000'), self.eva)

    def unidad(self, codigo, alicuota, propietario, edificio='default', **kw):
        return Unidad.objects.create(
            edificio=self.edificio if edificio == 'default' else edificio, codigo=codigo, alicuota=alicuota,
            propietario=propietario, **kw,
        )

    def dias(self, n):
        return self.hoy + timedelta(days=n)
