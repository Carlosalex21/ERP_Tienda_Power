"""
Aprovisiona (o resetea) el tenant demo público usado por la landing
("Probar demo en vivo" / catálogo público de ejemplo).

Es IDEMPOTENTE y pensado para correr tanto una vez (primera creación) como
periódicamente vía cron en producción, para que un visitante que "ensucia"
el demo (crea ventas, agota stock) no deje el estado roto para el siguiente:
cada corrida borra las transacciones/catálogo anteriores del tenant demo y
vuelve a sembrar el mismo set de datos de ejemplo.

Uso:
    python manage.py seed_demo_tenant
"""
from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.tenants.models import Client
from apps.tenants.services.tenant_service import TenantService, TenantCreationError

DEMO_SCHEMA = "demo"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "DemoERP2026!"
DEMO_EMAIL = "demo@erpsystem.local"

# Catálogo de ejemplo. "Refresco Cola 350ml" se deja a propósito con poco
# stock y alto volumen de venta reciente: es el producto que dispara la
# "Predicción de Quiebre de Stock" en el dashboard demo, para que un
# visitante vea esa función en acción sin tener que buscarla.
PRODUCTOS_DEMO = [
    {"nombre": "Refresco Cola 350ml", "sku": "DEMO-BEB-001", "precio": Decimal("1.20"), "cantidad": 9, "stock_minimo": 15, "categoria": "Bebidas", "venta_diaria_objetivo": 3.5},
    {"nombre": "Agua Mineral 600ml", "sku": "DEMO-BEB-002", "precio": Decimal("0.80"), "cantidad": 120, "stock_minimo": 20, "categoria": "Bebidas", "venta_diaria_objetivo": 1.0},
    {"nombre": "Jugo de Naranja 1L", "sku": "DEMO-BEB-003", "precio": Decimal("2.50"), "cantidad": 40, "stock_minimo": 10, "categoria": "Bebidas", "venta_diaria_objetivo": 0.6},
    {"nombre": "Papas Fritas 150g", "sku": "DEMO-SNK-001", "precio": Decimal("1.75"), "cantidad": 60, "stock_minimo": 15, "categoria": "Snacks", "venta_diaria_objetivo": 0.8},
    {"nombre": "Chocolate Barra 90g", "sku": "DEMO-SNK-002", "precio": Decimal("1.10"), "cantidad": 8, "stock_minimo": 20, "categoria": "Snacks", "venta_diaria_objetivo": 0.1},
    {"nombre": "Galletas Surtidas 200g", "sku": "DEMO-SNK-003", "precio": Decimal("2.00"), "cantidad": 55, "stock_minimo": 12, "categoria": "Snacks", "venta_diaria_objetivo": 0.5},
    {"nombre": "Audífonos Bluetooth", "sku": "DEMO-ELE-001", "precio": Decimal("18.99"), "cantidad": 14, "stock_minimo": 5, "categoria": "Electrónica", "venta_diaria_objetivo": 0.3},
    {"nombre": "Cargador USB-C 20W", "sku": "DEMO-ELE-002", "precio": Decimal("9.50"), "cantidad": 30, "stock_minimo": 8, "categoria": "Electrónica", "venta_diaria_objetivo": 0.4},
    {"nombre": "Power Bank 10000mAh", "sku": "DEMO-ELE-003", "precio": Decimal("22.00"), "cantidad": 3, "stock_minimo": 5, "categoria": "Electrónica", "venta_diaria_objetivo": 0.05},
    {"nombre": "Detergente Líquido 1L", "sku": "DEMO-HOG-001", "precio": Decimal("3.20"), "cantidad": 45, "stock_minimo": 10, "categoria": "Hogar", "venta_diaria_objetivo": 0.4},
    {"nombre": "Papel Higiénico x4", "sku": "DEMO-HOG-002", "precio": Decimal("2.80"), "cantidad": 70, "stock_minimo": 15, "categoria": "Hogar", "venta_diaria_objetivo": 0.7},
    {"nombre": "Café Molido 500g", "sku": "DEMO-HOG-003", "precio": Decimal("4.50"), "cantidad": 25, "stock_minimo": 10, "categoria": "Hogar", "venta_diaria_objetivo": 0.35},
]

CLIENTES_DEMO = [
    {"nombre": "María González", "telefono": "0414-1110001", "documento": "V-11100011"},
    {"nombre": "Carlos Pérez", "telefono": "0414-1110002", "documento": "V-11100022"},
    {"nombre": "Ana Rodríguez", "telefono": "0414-1110003", "documento": "V-11100033"},
    {"nombre": "Luis Fernández", "telefono": "0414-1110004", "documento": "V-11100044"},
    {"nombre": "Comercial El Ahorro, C.A.", "telefono": "0212-1110005", "documento": "J-11100055"},
]

DIAS_HISTORIAL = 30

# Tasa Bs./USD del demo: arranca en TASA_DEMO_INICIAL y sube un poco cada día
# (como en la vida real) para que el selector "$ / Bs." del panel muestre
# conversiones con historia. El catálogo se precia en USD y el costo es un
# porcentaje del precio, para que el "valor del inventario" no salga en 0.
TASA_DEMO_INICIAL = Decimal("140.00")
TASA_DEMO_ALZA_DIARIA = Decimal("0.35")
MARGEN_COSTO_DEMO = Decimal("0.62")


class Command(BaseCommand):
    help = "Crea (si no existe) y resetea con datos de ejemplo el tenant demo público de la landing."

    def handle(self, *args, **options):
        tenant = self._asegurar_tenant()
        with tenant_context(tenant):
            self._resetear_datos(tenant)
        self.stdout.write(self.style.SUCCESS(f"Tenant demo ('{DEMO_SCHEMA}') listo con datos de ejemplo."))

    def _asegurar_tenant(self) -> Client:
        try:
            return Client.objects.get(schema_name=DEMO_SCHEMA)
        except Client.DoesNotExist:
            pass
        self.stdout.write("Tenant demo no existe todavía -- aprovisionando...")
        try:
            tenant = TenantService.create_tenant(
                username=DEMO_USERNAME,
                email=DEMO_EMAIL,
                password=DEMO_PASSWORD,
                first_name="Demo",
                last_name="ERP",
                nombre_empresa="Tienda Demo ERP",
                subdomain=DEMO_SCHEMA,
                tipo_negocio="retail",
                pais_codigo="VE",
                # Larguísimo a propósito: el tenant demo nunca debe toparse
                # con la pantalla de "suscripción vencida" que ve un tenant
                # real -- no es un cliente de prueba, es la vitrina pública.
                trial_days=3650,
            )
        except TenantCreationError as exc:
            raise SystemExit(f"No se pudo crear el tenant demo: {exc}")
        return tenant

    def _resetear_datos(self, tenant: Client) -> None:
        from django.contrib.auth.models import User as TenantUser
        from apps.usuarios.models import Rol, UserMetadata
        from apps.clientes.models import Cliente
        from apps.inventario.models import Producto, Categoriaproducto, Almacen
        from apps.configuracion.models import Moneda, TasaCambio, Configuracioniva
        from apps.facturacion.models import Factura, Detallefactura, MetodoPago

        with transaction.atomic():
            # 1) Limpieza de lo transaccional/catálogo de corridas anteriores
            # (PROTECT en Detallefactura.variante no aplica aquí: este
            # catálogo demo no usa variantes).
            Detallefactura.objects.all().delete()
            Factura.objects.all().delete()
            Cliente.objects.all().delete()
            Producto.objects.all().delete()
            Categoriaproducto.objects.all().delete()

            # 2) Usuario demo: ya lo crea `_seed_tenant_defaults` como admin
            # con la contraseña fija de arriba -- solo lo confirmamos activo
            # por si una corrida previa lo hubiese desactivado a mano.
            admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador", defaults={"codigo": "admin"})
            demo_user, _ = TenantUser.objects.update_or_create(
                username=DEMO_USERNAME,
                defaults={"email": DEMO_EMAIL, "first_name": "Demo", "last_name": "ERP", "is_active": True, "is_staff": True, "is_superuser": True},
            )
            demo_user.set_password(DEMO_PASSWORD)
            demo_user.save()
            UserMetadata.objects.update_or_create(user=demo_user, defaults={"rol": admin_rol})

            almacen, _ = Almacen.objects.get_or_create(nombre="Almacén Principal", defaults={"direccion": "Dirección por configurar"})
            moneda_base = Moneda.objects.filter(es_predeterminada=True).first()
            usd, _ = Moneda.objects.get_or_create(
                codigo="USD", defaults={"nombre": "Dólar estadounidense", "simbolo": "$", "es_predeterminada": False, "activa": True},
            )
            hoy = timezone.localdate()
            tasa_por_dia = {
                hoy - timedelta(days=d): TASA_DEMO_INICIAL + TASA_DEMO_ALZA_DIARIA * (DIAS_HISTORIAL - d)
                for d in range(DIAS_HISTORIAL, -1, -1)
            }
            TasaCambio.objects.filter(moneda=usd).delete()
            for fecha_tasa, valor in tasa_por_dia.items():
                tasa_obj = TasaCambio.objects.create(moneda=usd, tasa=valor, fuente="Demo", activa=True)
                # `fecha` es auto_now_add: se corrige después de crear.
                TasaCambio.objects.filter(pk=tasa_obj.pk).update(fecha=fecha_tasa)
            iva_general = Configuracioniva.objects.filter(activo=True).order_by("porcentaje_iva").last()
            metodo_efectivo, _ = MetodoPago.objects.get_or_create(nombre="Efectivo", defaults={"tipo_metodo": "efectivo", "activo": True})

            # 3) Categorías + catálogo.
            categorias = {}
            for nombre_categoria in {p["categoria"] for p in PRODUCTOS_DEMO}:
                categorias[nombre_categoria], _ = Categoriaproducto.objects.get_or_create(nombre=nombre_categoria)

            productos = {}
            for info in PRODUCTOS_DEMO:
                productos[info["sku"]] = Producto.objects.create(
                    nombre=info["nombre"],
                    sku=info["sku"],
                    precio=info["precio"],
                    cantidad=info["cantidad"],
                    stock_minimo=info["stock_minimo"],
                    categoria=categorias[info["categoria"]],
                    almacen=almacen,
                    moneda=usd,
                    costo_promedio=(info["precio"] * MARGEN_COSTO_DEMO).quantize(Decimal("0.01")),
                    configuracion_iva=iva_general,
                    disponible_online=True,
                    tipo="simple",
                    activo=True,
                )

            # 4) Clientes.
            clientes = [
                Cliente.objects.create(nombre=c["nombre"], telefono=c["telefono"], documento=c["documento"], tipo_documento="V", activo=True)
                for c in CLIENTES_DEMO
            ]

            # 5) Historial de ventas de los últimos `DIAS_HISTORIAL` días,
            # calibrado para que cada producto ronde su
            # `venta_diaria_objetivo` -- así el dashboard (gráfico, top
            # productos, predicción de quiebre) se ve como un negocio real
            # y no como una tabla vacía.
            iva_pct = (iva_general.porcentaje_iva / Decimal("100")) if iva_general else Decimal("0")
            ahora = timezone.now()
            for dia_offset in range(DIAS_HISTORIAL, -1, -1):
                fecha = ahora - timedelta(days=dia_offset)
                for info in PRODUCTOS_DEMO:
                    objetivo = info["venta_diaria_objetivo"]
                    # Poisson aproximado con aleatoriedad simple: la mayoría
                    # de los días vende "objetivo" unidades +/- variación;
                    # algunos días no vende nada (producto de baja rotación).
                    unidades = max(0, round(random.gauss(objetivo, max(objetivo * 0.4, 0.2))))
                    if unidades <= 0:
                        continue
                    producto = productos[info["sku"]]
                    cliente = random.choice(clientes)
                    # ~1 de cada 3 ventas se cobra en bolívares (a la tasa
                    # del día), el resto en dólares -- como un comercio real.
                    tasa_dia = tasa_por_dia[fecha.date()] if fecha.date() in tasa_por_dia else TASA_DEMO_INICIAL
                    en_bolivares = random.random() < 0.33
                    moneda_factura = moneda_base if en_bolivares else usd
                    tasa_factura = Decimal("1.000000") if en_bolivares else tasa_dia
                    precio = (info["precio"] * tasa_dia).quantize(Decimal("0.01")) if en_bolivares else info["precio"]
                    subtotal = (precio * unidades).quantize(Decimal("0.01"))
                    iva_monto = (subtotal * iva_pct).quantize(Decimal("0.01"))
                    total = subtotal + iva_monto

                    factura = Factura(
                        usuario=demo_user,
                        vendedor=demo_user,
                        condicion_pago="contado",
                        cliente=cliente,
                        fecha_operacion=fecha,
                        moneda=moneda_factura,
                        tasa_cambio=tasa_factura,
                        subtotal=subtotal,
                        base_imponible=subtotal,
                        iva_total=iva_monto,
                        total=total,
                        subtotal_base=(subtotal * tasa_factura).quantize(Decimal("0.01")),
                        base_imponible_base=(subtotal * tasa_factura).quantize(Decimal("0.01")),
                        iva_base=(iva_monto * tasa_factura).quantize(Decimal("0.01")),
                        total_base=(total * tasa_factura).quantize(Decimal("0.01")),
                        almacen=almacen,
                        estado="pagado",
                        metodo_pago=metodo_efectivo,
                        activo=True,
                    )
                    factura.save()
                    Detallefactura.objects.create(
                        factura=factura,
                        producto=producto,
                        cantidad=unidades,
                        precio_unitario=precio,
                        subtotal_linea=subtotal,
                        iva_linea=iva_monto,
                        total_linea=total,
                    )
