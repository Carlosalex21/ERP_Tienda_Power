"""
Aprovisiona (o resetea) los dos tenants demo de la vertical de inmuebles:

- `democondominios`: administradora con un edificio de 12 unidades, tres meses
  de cobranza, morosos, pagos por revisar y portal del condómino.
- `demoinmobiliaria`: inmobiliaria con propiedades publicadas (con fotos),
  contratos vigentes, un moroso, liquidaciones y consultas de interesados.

Es IDEMPOTENTE: cada corrida borra los datos de inmuebles del demo y los vuelve a
sembrar, así un visitante que "ensucia" el demo no deja el estado roto.

Uso:
    python manage.py seed_demo_inmuebles                 # ambos
    python manage.py seed_demo_inmuebles --solo condominios
"""
from __future__ import annotations

import io
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context
from PIL import Image, ImageDraw

from apps.tenants.models import Client
from apps.tenants.services.tenant_service import TenantCreationError, TenantService

PASSWORD = 'DemoERP2026!'
TASA_INICIAL = Decimal('140.00')
TASA_ALZA_DIARIA = Decimal('0.20')
DIAS_TASAS = 90

DEMOS = {
    'condominios': {
        'schema': 'democondominios', 'usuario': 'demo_condominios', 'email': 'demo+condominios@erpsystem.local',
        'nombre': 'Administradora Los Pinos', 'tipo': 'condominios',
    },
    'inmobiliaria': {
        'schema': 'demoinmobiliaria', 'usuario': 'demo_inmobiliaria', 'email': 'demo+inmobiliaria@erpsystem.local',
        'nombre': 'Inmobiliaria Horizonte', 'tipo': 'inmobiliaria',
    },
}

PERSONAS = [
    ('María González', 'V-12345678', '0414-5550101'), ('Carlos Pérez', 'V-13456789', '0414-5550102'),
    ('Ana Rodríguez', 'V-14567890', '0424-5550103'), ('Luis Fernández', 'V-15678901', '0416-5550104'),
    ('Elena Martínez', 'V-16789012', '0412-5550105'), ('José Ramírez', 'V-17890123', '0414-5550106'),
    ('Carmen Silva', 'V-18901234', '0424-5550107'), ('Pedro Navarro', 'V-19012345', '0416-5550108'),
    ('Rosa Herrera', 'V-20123456', '0412-5550109'), ('Miguel Torres', 'V-21234567', '0414-5550110'),
    ('Lucía Mendoza', 'V-22345678', '0424-5550111'), ('Andrés Castillo', 'V-23456789', '0416-5550112'),
]

GASTOS_MES = [
    ('vigilancia', 'Vigilancia 24 horas', Decimal('620.00')), ('aseo', 'Aseo y limpieza de áreas comunes', Decimal('280.00')),
    ('electricidad', 'Electricidad áreas comunes', Decimal('150.00')), ('agua', 'Consumo de agua', Decimal('210.00')),
    ('ascensor', 'Mantenimiento de ascensor', Decimal('180.00')), ('administracion', 'Honorarios de administración', Decimal('240.00')),
    ('mantenimiento', 'Reparaciones menores', Decimal('95.00')),
]


def periodo_con_offset(hoy: date, meses: int) -> str:
    total = hoy.year * 12 + (hoy.month - 1) + meses
    return f'{total // 12:04d}-{total % 12 + 1:02d}'


def foto_demo(texto: str, color: tuple[int, int, int], variante: int) -> bytes:
    """Imagen de ejemplo (degradado + formas) -- el demo no depende de fotos externas."""
    ancho, alto = 1200, 800
    img = Image.new('RGB', (ancho, alto), color)
    dibujo = ImageDraw.Draw(img)
    for y in range(alto):
        factor = y / alto
        dibujo.line([(0, y), (ancho, y)], fill=tuple(int(c * (1 - 0.45 * factor) + 255 * 0.12 * factor) for c in color))
    desplazamiento = variante * 90
    dibujo.rectangle([180 + desplazamiento, 330, 560 + desplazamiento, 700], fill=(255, 255, 255, 40), outline=(255, 255, 255), width=4)
    dibujo.rectangle([640 + desplazamiento // 2, 420, 1000, 700], outline=(255, 255, 255), width=4)
    for i in range(3):
        dibujo.rectangle([230 + desplazamiento + i * 110, 380, 290 + desplazamiento + i * 110, 450], outline=(255, 255, 255), width=3)
    dibujo.ellipse([960, 90, 1090, 220], fill=(255, 236, 170))
    dibujo.text((60, 60), texto, fill=(255, 255, 255))
    salida = io.BytesIO()
    img.save(salida, 'JPEG', quality=82)
    return salida.getvalue()


class Command(BaseCommand):
    help = 'Crea (si no existen) y resetea los tenants demo de condominios e inmobiliaria.'

    def add_arguments(self, parser):
        parser.add_argument('--solo', choices=sorted(DEMOS), help='Sembrar solo uno de los dos demos.')

    def handle(self, *args, **options):
        for clave in ([options['solo']] if options['solo'] else list(DEMOS)):
            demo = DEMOS[clave]
            tenant = self._asegurar_tenant(demo)
            with tenant_context(tenant):
                with transaction.atomic():
                    self._preparar(demo)
                    {'condominios': self._sembrar_condominios, 'inmobiliaria': self._sembrar_inmobiliaria}[clave]()
            self.stdout.write(self.style.SUCCESS(f"Demo '{demo['schema']}' listo (usuario {demo['usuario']} / {PASSWORD})."))

    # -- infraestructura -------------------------------------------------------

    def _asegurar_tenant(self, demo) -> Client:
        try:
            return Client.objects.get(schema_name=demo['schema'])
        except Client.DoesNotExist:
            pass
        self.stdout.write(f"Tenant {demo['schema']} no existe todavía -- aprovisionando...")
        try:
            return TenantService.create_tenant(
                username=demo['usuario'], email=demo['email'], password=PASSWORD, first_name='Demo', last_name='ERP',
                nombre_empresa=demo['nombre'], subdomain=demo['schema'], tipo_negocio=demo['tipo'], pais_codigo='VE', trial_days=3650,
            )
        except TenantCreationError as exc:
            raise SystemExit(f'No se pudo crear el tenant demo: {exc}')

    def _preparar(self, demo) -> None:
        from django.contrib.auth.models import User
        from apps.configuracion.models import ConfiguracionEmpresa, Moneda, TasaCambio
        from apps.usuarios.models import Rol, UserMetadata
        from apps.inmuebles import models as m
        from apps.clientes.models import Cliente

        # Limpieza (en orden por las relaciones PROTECT).
        m.PagoReportado.objects.all().delete()
        m.ReciboAplicacion.objects.all().delete()
        m.Recibo.objects.all().delete()
        m.GastoPropiedad.objects.all().delete()
        m.Liquidacion.objects.all().delete()
        m.Cargo.objects.filter(tipo='mora').delete()
        m.Cargo.objects.all().delete()
        m.PeriodoCondominio.objects.all().delete()
        m.GastoComun.objects.all().delete()
        m.Contrato.objects.all().delete()
        for foto in m.UnidadFoto.objects.all():
            foto.imagen.delete(save=False)
        m.Unidad.objects.all().delete()
        m.MedioPago.objects.all().delete()
        m.Edificio.objects.all().delete()
        m.ConsultaPropiedad.objects.all().delete()
        m.PortalAcceso.objects.all().delete()
        Cliente.objects.all().delete()

        admin_rol, _ = Rol.objects.get_or_create(nombre='Administrador', defaults={'codigo': 'admin'})
        usuario, _ = User.objects.update_or_create(
            username=demo['usuario'], defaults={'email': demo['email'], 'first_name': 'Demo', 'last_name': 'ERP', 'is_active': True, 'is_staff': True, 'is_superuser': True},
        )
        usuario.set_password(PASSWORD)
        usuario.save()
        UserMetadata.objects.update_or_create(user=usuario, defaults={'rol': admin_rol})
        self.usuario = usuario

        empresa, _ = ConfiguracionEmpresa.objects.get_or_create(pk=1)
        empresa.nombre_comercial = demo['nombre']
        empresa.razon_social = f"{demo['nombre']}, C.A."
        empresa.rif = 'J-30123456-7'
        empresa.telefono = '0414-5551234'
        empresa.direccion = 'Av. Francisco de Miranda, Torre Demo, Caracas'
        empresa.save()

        usd, _ = Moneda.objects.get_or_create(codigo='USD', defaults={'nombre': 'Dólar estadounidense', 'simbolo': '$', 'es_predeterminada': False, 'activa': True})
        hoy = timezone.localdate()
        TasaCambio.objects.filter(moneda=usd).delete()
        for d in range(DIAS_TASAS, -1, -1):
            tasa = TasaCambio.objects.create(moneda=usd, tasa=TASA_INICIAL + TASA_ALZA_DIARIA * (DIAS_TASAS - d), fuente='Demo', activa=True)
            TasaCambio.objects.filter(pk=tasa.pk).update(fecha=hoy - timedelta(days=d))
        self.hoy = hoy
        self.tasa_hoy = TASA_INICIAL + TASA_ALZA_DIARIA * DIAS_TASAS

    def _personas(self, cantidad: int, desde: int = 0):
        from apps.clientes.models import Cliente
        return [
            Cliente.objects.create(nombre=n, documento=d, tipo_documento='V', telefono=t, email=f'{n.split()[0].lower()}{i + desde}@demo.com', activo=True)
            for i, (n, d, t) in enumerate(PERSONAS[desde:desde + cantidad])
        ]

    # -- condominios -----------------------------------------------------------

    def _sembrar_condominios(self) -> None:
        from apps.inmuebles import models as m
        from apps.inmuebles.services import cobranza, condominio, portal

        random.seed(7)
        edificio = m.Edificio.objects.create(
            nombre='Residencias Los Pinos', direccion='Urb. Los Pinos, Av. Principal, Caracas', rif='J-31234567-8', dia_vencimiento=5,
            mora_pct_mensual=Decimal('2.00'), dias_gracia=3, fondo_reserva_pct=Decimal('5.00'), portal_muestra_morosidad=True,
        )
        m.MedioPago.objects.create(edificio=edificio, tipo='pago_movil', titular='Condominio Residencias Los Pinos', documento_titular='J-31234567-8', banco='Banesco', numero_cuenta='0414-5559900', moneda='VES', instrucciones='Indica la unidad en el concepto del pago.')
        m.MedioPago.objects.create(edificio=edificio, tipo='transferencia', titular='Condominio Residencias Los Pinos', documento_titular='J-31234567-8', banco='Mercantil', numero_cuenta='0105-0123-45-1234567890', moneda='VES')
        m.MedioPago.objects.create(edificio=None, tipo='zelle', titular='Administradora Los Pinos', numero_cuenta='pagos@administradoralospinos.com', moneda='USD', instrucciones='Envía el comprobante por el portal.')

        propietarios = self._personas(12)
        alicuotas = [Decimal('8.3300')] * 11
        alicuotas.append(Decimal('100.0000') - sum(alicuotas))  # la última cierra el 100 exacto
        unidades = []
        for indice, (cliente, alicuota) in enumerate(zip(propietarios, alicuotas)):
            piso, letra = indice // 4 + 1, 'ABCD'[indice % 4]
            unidades.append(m.Unidad.objects.create(
                edificio=edificio, codigo=f'Apto {piso}-{letra}', tipo='apartamento', alicuota=alicuota, area_m2=Decimal('78') + indice,
                propietario=cliente, estado='ocupada',
            ))

        # Tres meses ya emitidos, con distintos niveles de pago.
        patrones = {0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 2, 8: 1, 9: 0, 10: 2, 11: 3}  # unidades -> meses pagados (de los 3)
        for atras in (3, 2, 1):
            periodo = periodo_con_offset(self.hoy, -atras)
            for categoria, descripcion, base in GASTOS_MES:
                variacion = Decimal(str(round(random.uniform(0.92, 1.1), 3)))
                m.GastoComun.objects.create(
                    edificio=edificio, periodo=periodo, categoria=categoria, descripcion=descripcion, monto_usd=(base * variacion).quantize(Decimal('0.01')),
                    fecha=cobranza.primer_dia(periodo) + timedelta(days=10), usuario=self.usuario,
                )
            emitido = condominio.emitir_periodo(edificio, periodo, usuario=self.usuario)
            # El período se "emitió" en su momento, no hoy.
            siguiente = cobranza.sumar_meses(periodo, 1)
            emision = cobranza.primer_dia(siguiente) + timedelta(days=1)
            vencimiento = cobranza.fecha_en_mes(siguiente, 5)
            m.PeriodoCondominio.objects.filter(pk=emitido.pk).update(fecha_emision=emision, fecha_vencimiento=vencimiento)
            m.Cargo.objects.filter(periodo_condominio=emitido).update(fecha_emision=emision, fecha_vencimiento=vencimiento)

            for indice, unidad in enumerate(unidades):
                # `patrones` dice cuántos de los 3 meses pagó: paga los más antiguos primero.
                mes_numero = 4 - atras  # 1 = el más antiguo
                if mes_numero <= patrones[indice]:
                    cuota = m.Cargo.objects.get(periodo_condominio=emitido, unidad=unidad)
                    fecha_pago = min(vencimiento + timedelta(days=random.randint(-3, 6)), self.hoy)
                    en_bs = random.random() < 0.7
                    monto_usd = cuota.monto_usd
                    cobranza.registrar_recibo(
                        usuario=self.usuario, unidad=unidad, fecha=fecha_pago,
                        monto_pago=(monto_usd * self.tasa_hoy).quantize(Decimal('0.01')) if en_bs else monto_usd,
                        moneda_pago='VES' if en_bs else 'USD', tasa=self.tasa_hoy, metodo='pago_movil' if en_bs else 'zelle',
                        referencia=f'{random.randint(100000, 999999)}', banco='Banesco' if en_bs else '', cargos=[cuota],
                    )

        # Pago adelantado: la unidad 12 deja saldo a favor.
        cobranza.registrar_recibo(usuario=self.usuario, unidad=unidades[11], fecha=self.hoy, monto_pago=Decimal('150.00'), moneda_pago='USD', metodo='zelle', referencia='ZELLE-ADELANTO')

        # Mes en curso: gastos cargados, listo para previsualizar y emitir.
        periodo_actual = cobranza.periodo_de(self.hoy)
        for categoria, descripcion, base in GASTOS_MES[:5]:
            m.GastoComun.objects.create(edificio=edificio, periodo=periodo_actual, categoria=categoria, descripcion=descripcion, monto_usd=base, fecha=self.hoy, usuario=self.usuario)

        cobranza.aplicar_mora(self.hoy)

        # Enlaces de portal y dos avisos de pago pendientes de revisión.
        accesos = {u.propietario_id: portal.obtener_o_crear_acceso(u.propietario) for u in unidades}
        for indice, referencia in ((8, '554433'), (10, '112233')):
            unidad = unidades[indice]
            pendiente = list(m.Cargo.objects.filter(unidad=unidad, estado='pendiente', tipo='cuota_condominio').order_by('fecha_vencimiento')[:1])
            if pendiente:
                portal.reportar_pago(
                    accesos[unidad.propietario_id], unidad_id=unidad.pk, fecha_pago=self.hoy, monto_pago=(pendiente[0].saldo_usd * self.tasa_hoy).quantize(Decimal('0.01')),
                    moneda_pago='VES', metodo='pago_movil', referencia=referencia, banco='Banesco', cargos_ids=[pendiente[0].pk], nota='Pago de la cuota atrasada',
                )
        moroso = unidades[9]
        self.stdout.write(f"Portal de ejemplo (moroso {moroso.codigo}): /portal/{accesos[moroso.propietario_id].token}")
        self.stdout.write(f"Portal de ejemplo (al día {unidades[0].codigo}): /portal/{accesos[unidades[0].propietario_id].token}")

    # -- inmobiliaria ----------------------------------------------------------

    def _sembrar_inmobiliaria(self) -> None:
        from apps.inmuebles import models as m
        from apps.inmuebles.services import cobranza, contratos, liquidaciones

        m.MedioPago.objects.create(edificio=None, tipo='zelle', titular='Inmobiliaria Horizonte', numero_cuenta='cobros@inmobiliariahorizonte.com', moneda='USD')
        m.MedioPago.objects.create(edificio=None, tipo='transferencia', titular='Inmobiliaria Horizonte, C.A.', documento_titular='J-30123456-7', banco='Banesco', numero_cuenta='0134-0123-45-1234567890', moneda='VES')

        propietarios = self._personas(4)
        inquilinos = self._personas(4, desde=4)

        def propiedad(codigo, tipo, dueno, **kw):
            return m.Unidad.objects.create(codigo=codigo, tipo=tipo, propietario=dueno, alicuota=0, **kw)

        fotos_plan = [
            ((64, 120, 180), 'Apartamento'), ((46, 139, 87), 'Casa'), ((186, 120, 60), 'Local'), ((120, 90, 160), 'Townhouse'),
            ((60, 130, 130), 'Terreno'),
        ]

        apto_altamira = propiedad(
            'ALT-01', 'apartamento', propietarios[0], estado='disponible', operacion='alquiler', publicada=True,
            titulo='Moderno apartamento en Altamira', descripcion='Apartamento remodelado, cocina equipada, balcón con vista al Ávila, a pasos del Metro. Edificio con planta eléctrica y vigilancia 24 horas.',
            zona='Altamira', ciudad='Caracas', direccion='Av. Principal de Altamira', canon_usd=Decimal('450'), habitaciones=2, banos=2, estacionamientos=1,
            area_m2=Decimal('85'), area_construida_m2=Decimal('85'), amenidades=['Planta eléctrica', 'Vigilancia 24h', 'Ascensor', 'Balcón'],
        )
        casa_venta = propiedad(
            'LAG-01', 'casa', propietarios[1], estado='disponible', operacion='venta', publicada=True, titulo='Casa familiar en La Lagunita',
            descripcion='Amplia casa de dos niveles en urbanización cerrada, jardín, maletero y cuarto de servicio. Lista para mudarse.',
            zona='La Lagunita', ciudad='Caracas', direccion='Calle 5', precio_venta_usd=Decimal('285000'), habitaciones=4, banos=4, estacionamientos=3,
            area_m2=Decimal('520'), area_construida_m2=Decimal('360'), amenidades=['Jardín', 'Piscina', 'Urbanización cerrada', 'Cuarto de servicio'],
        )
        local = propiedad(
            'MER-01', 'local', propietarios[2], estado='disponible', operacion='alquiler', publicada=True, titulo='Local esquinero en Las Mercedes',
            descripcion='Local a pie de calle con alto flujo peatonal, ideal para restaurante o tienda. Vitrinas amplias y baño.',
            zona='Las Mercedes', ciudad='Caracas', direccion='Calle Veracruz', canon_usd=Decimal('1800'), banos=1, estacionamientos=2,
            area_m2=Decimal('120'), area_construida_m2=Decimal('120'), amenidades=['Vitrinas', 'Aire acondicionado'],
        )
        townhouse = propiedad(
            'TRU-01', 'townhouse', propietarios[3], estado='disponible', operacion='alquiler_venta', publicada=True, titulo='Townhouse en conjunto residencial',
            descripcion='Townhouse de 3 niveles en conjunto con parque y vigilancia. Opción de alquiler o venta.',
            zona='Trigal Norte', ciudad='Valencia', direccion='Conjunto Los Samanes', canon_usd=Decimal('1100'), precio_venta_usd=Decimal('120000'),
            habitaciones=3, banos=3, estacionamientos=2, area_m2=Decimal('210'), area_construida_m2=Decimal('190'), amenidades=['Parque', 'Vigilancia 24h', 'Terraza'],
        )
        terreno = propiedad(
            'MAR-01', 'terreno', propietarios[1], estado='disponible', operacion='venta', publicada=True, titulo='Terreno cerca de la playa en Margarita',
            descripcion='Terreno plano con documentos al día, a 5 minutos de la playa. Ideal para posada o desarrollo residencial.',
            zona='Pampatar', ciudad='Porlamar', direccion='Sector El Cardón', precio_venta_usd=Decimal('65000'), area_m2=Decimal('900'), amenidades=['Documentos al día', 'Cerca de la playa'],
        )
        oficina = propiedad('CHA-01', 'oficina', propietarios[2], estado='ocupada', zona='Chacao', ciudad='Caracas', direccion='Av. Libertador', area_m2=Decimal('95'))
        apto_palos = propiedad('PAL-01', 'apartamento', propietarios[0], estado='ocupada', zona='Los Palos Grandes', ciudad='Caracas', direccion='3ra Transversal', habitaciones=3, banos=2, area_m2=Decimal('110'))
        apto_rosal = propiedad('ROS-01', 'apartamento', propietarios[3], estado='ocupada', zona='El Rosal', ciudad='Caracas', direccion='Av. Venezuela', habitaciones=1, banos=1, area_m2=Decimal('55'))

        for indice, unidad in enumerate((apto_altamira, casa_venta, local, townhouse, terreno)):
            color, etiqueta = fotos_plan[indice]
            for n in range(3):
                m.UnidadFoto.objects.create(
                    unidad=unidad, orden=n, es_portada=(n == 0),
                    imagen=ContentFile(foto_demo(f'{etiqueta} · {unidad.codigo}', tuple(min(255, c + n * 18) for c in color), n), name=f'{unidad.codigo}-{n}.jpg'),
                )

        hoy = self.hoy
        inicio_antiguo = hoy.replace(day=1) - timedelta(days=95)

        def contrato(unidad, inquilino, inicio, fin, canon, honorario, **kw):
            c = contratos.crear_contrato(usuario=self.usuario, unidad=unidad, inquilino=inquilino, fecha_inicio=inicio, fecha_fin=fin, canon_usd=canon, honorario_pct=honorario, deposito_usd=kw.pop('deposito', canon), dia_pago=5, **kw)
            # Contrato "ya en marcha": se retrocede la fecha de alta para generar los meses transcurridos.
            m.Contrato.objects.filter(pk=c.pk).update(fecha_creacion=timezone.make_aware(datetime.combine(inicio, time(9, 0))))
            c.refresh_from_db()
            contratos.activar_contrato(c, cobrar_deposito=False)
            contratos.generar_cargos_contrato(c)
            return c

        c_oficina = contrato(oficina, inquilinos[0], inicio_antiguo, hoy + timedelta(days=25), Decimal('900'), Decimal('10'), mora_pct_mensual=Decimal('3'))
        c_palos = contrato(apto_palos, inquilinos[1], inicio_antiguo, hoy + timedelta(days=210), Decimal('520'), Decimal('10'), ajuste_anual_pct=Decimal('8'))
        c_rosal = contrato(apto_rosal, inquilinos[2], inicio_antiguo, hoy + timedelta(days=150), Decimal('380'), Decimal('12'), mora_pct_mensual=Decimal('3'))

        # Cobros: la oficina y el apto de Los Palos al día; el de El Rosal debe dos meses.
        for c in (c_oficina, c_palos):
            for cargo in m.Cargo.objects.filter(contrato=c, tipo='canon').order_by('periodo'):
                if cargo.periodo < cobranza.periodo_de(hoy):
                    cobranza.registrar_recibo(
                        usuario=self.usuario, unidad=c.unidad, fecha=min(cargo.fecha_vencimiento + timedelta(days=1), hoy), monto_pago=cargo.monto_usd, moneda_pago='USD',
                        tasa=self.tasa_hoy, metodo='zelle', referencia=f'Z{cargo.pk}', cargos=[cargo],
                    )
        for cargo in m.Cargo.objects.filter(contrato=c_rosal, tipo='canon').order_by('periodo')[:1]:
            cobranza.registrar_recibo(usuario=self.usuario, unidad=apto_rosal, fecha=cargo.fecha_vencimiento, monto_pago=cargo.monto_usd, moneda_pago='USD', tasa=self.tasa_hoy, metodo='transferencia', referencia=f'T{cargo.pk}', cargos=[cargo])
        cobranza.aplicar_mora(hoy)

        # Liquidaciones: una ya pagada al dueño de la oficina, y gastos pendientes para el de Los Palos.
        m.GastoPropiedad.objects.create(unidad=apto_palos, fecha=hoy - timedelta(days=12), descripcion='Reparación de filtración en baño', monto_usd=Decimal('85.00'), usuario=self.usuario)
        liq = liquidaciones.generar_liquidacion(propietarios[2], usuario=self.usuario)
        liquidaciones.pagar_liquidacion(liq, fecha=hoy - timedelta(days=3), referencia='TRF-884422')
        # Cobros del mes en curso (quedan pendientes de liquidar a sus dueños).
        for c in (c_oficina, c_palos):
            actual = m.Cargo.objects.filter(contrato=c, tipo='canon', periodo=cobranza.periodo_de(hoy), estado='pendiente').first()
            if actual:
                cobranza.registrar_recibo(
                    usuario=self.usuario, unidad=c.unidad, fecha=hoy, monto_pago=(actual.monto_usd * self.tasa_hoy).quantize(Decimal('0.01')), moneda_pago='VES',
                    tasa=self.tasa_hoy, metodo='pago_movil', referencia=f'PM{actual.pk}', banco='Banesco', cargos=[actual],
                )
        liquidaciones.generar_liquidacion(propietarios[0], usuario=self.usuario, observaciones='Liquidación del período.')

        # Interesados.
        m.ConsultaPropiedad.objects.create(unidad=apto_altamira, nombre='Gabriela Morales', telefono='0414-7771122', email='gabriela@correo.com', mensaje='Hola, ¿el apartamento sigue disponible? Me gustaría visitarlo este fin de semana.')
        m.ConsultaPropiedad.objects.create(unidad=casa_venta, nombre='Ricardo Blanco', telefono='0424-8883344', mensaje='¿Aceptan financiamiento o solo de contado?', estado='contactada', notas='Lo llamé: viene el sábado a las 10.')
        m.ConsultaPropiedad.objects.create(unidad=local, nombre='Restaurante El Fogón', telefono='0212-5559900', email='gerencia@elfogon.com', mensaje='Buscamos local con salida de humos. ¿Es posible?')
