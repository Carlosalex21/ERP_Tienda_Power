"""
Repara el Libro de Compra/Venta existente, en dos frentes:

1. Antes, una factura se registraba en el Libro al CREARSE desde el panel
   (POS), momento en el que normalmente todavía estaba en estado
   'borrador' -- sin correlativo asignado todavía -- así que esas líneas
   quedaron con `numero_documento=''`. Las ventas del catálogo público, que
   se crean por un camino distinto, ni siquiera llegaban a registrarse.
   Ambos casos se arreglaron en el código (ver `Factura.save()` y
   `libros_service.py`); este comando reconstruye, para el historial ya
   guardado, la línea del Libro de cada factura/nota que sí tiene un
   número fiscal real, con los montos correctos en moneda base.

2. Esas líneas viejas con `numero_documento` vacío (u otro que ya no
   corresponde a ningún documento real) quedan huérfanas y se desactivan
   (baja lógica, nunca se borran de verdad) en vez de dejarlas mezcladas
   con las líneas válidas.

Uso:
    python manage.py backfill_libro_moneda_base --dry-run   # solo reporta
    python manage.py backfill_libro_moneda_base              # aplica
    python manage.py backfill_libro_moneda_base --schema=prueba2
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = "Reconstruye el Libro de Compra/Venta a partir de las facturas/notas reales y desactiva las líneas huérfanas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo reporta lo que cambiaría, sin guardar nada.")
        parser.add_argument("--schema", type=str, default=None, help="Limitar a un solo schema (nombre de tenant).")

    def handle(self, *args, **options):
        from apps.tenants.models import Client

        dry_run = options["dry_run"]
        schema_filtro = options["schema"]

        tenants = Client.objects.exclude(schema_name="public")
        if schema_filtro:
            tenants = tenants.filter(schema_name=schema_filtro)

        total_reconstruidas = 0
        total_huerfanas = 0

        for tenant in tenants:
            with schema_context(tenant.schema_name):
                reconstruidas, huerfanas = self._procesar_schema(tenant.schema_name, dry_run)
                total_reconstruidas += reconstruidas
                total_huerfanas += huerfanas

        accion = "Se reconstruirían" if dry_run else "Se reconstruyeron"
        accion2 = "se desactivarían" if dry_run else "se desactivaron"
        self.stdout.write(self.style.SUCCESS(
            f"{accion} {total_reconstruidas} línea(s) del Libro a partir de sus documentos reales; "
            f"{total_huerfanas} línea(s) huérfana(s) {accion2}."
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: no se guardó nada. Vuelve a correr sin --dry-run para aplicar."))

    def _procesar_schema(self, schema_name: str, dry_run: bool) -> tuple[int, int]:
        from apps.facturacion.models import Factura, LibroCompraVenta, NotaCredito, NotaDebito
        from apps.facturacion.services.libros_service import registrar_factura_en_libro, registrar_en_libro_compra_venta
        from decimal import ROUND_HALF_UP, Decimal

        def _round(value) -> Decimal:
            return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        reconstruidas = 0
        numeros_validos: set[tuple[str, str]] = set()  # (tipo_documento, numero_documento)

        # --- Facturas: recrear/actualizar su línea a partir del documento real ---
        for factura in Factura.objects.filter(correlativo__isnull=False).exclude(correlativo=""):
            numeros_validos.add(("Factura", factura.correlativo))
            if dry_run:
                existente = LibroCompraVenta.objects.filter(
                    tipo_documento="Factura", numero_documento=factura.correlativo,
                ).first()
                nuevo_total = _round(factura.total_base)
                if not existente or existente.total != nuevo_total or not existente.numero_control:
                    self.stdout.write(
                        f"[{schema_name}] Factura {factura.correlativo}: "
                        f"total Libro {existente.total if existente else '(sin línea)'} -> {nuevo_total}"
                    )
                    reconstruidas += 1
                continue
            antes = LibroCompraVenta.objects.filter(
                tipo_documento="Factura", numero_documento=factura.correlativo,
            ).values_list("total", flat=True).first()
            registrar_factura_en_libro(factura)
            if antes != _round(factura.total_base):
                reconstruidas += 1

        # --- Notas de Crédito ---
        for nota in NotaCredito.objects.filter(activo=True).select_related("factura"):
            numeros_validos.add(("Nota de Crédito", nota.numero_nota))
            factura = nota.factura
            if not factura or not factura.total:
                continue
            proporcion = nota.total / factura.total
            nuevos = dict(
                base_imponible=-_round(factura.base_imponible_base * proporcion),
                iva=-_round(factura.iva_base * proporcion),
                retencion=-_round(factura.retencion_base * proporcion),
                total=-_round(factura.total_base * proporcion),
            )
            if self._upsert(schema_name, "Nota de Crédito", nota.numero_nota, nota.numero_control,
                             factura, nuevos, registrar_en_libro_compra_venta, dry_run):
                reconstruidas += 1

        # --- Notas de Débito ---
        for nota in NotaDebito.objects.filter(activo=True).select_related("factura"):
            numeros_validos.add(("Nota de Débito", nota.numero_nota))
            factura = nota.factura
            if not factura or not factura.total:
                continue
            proporcion = nota.total / factura.total
            nuevos = dict(
                base_imponible=_round(factura.base_imponible_base * proporcion),
                iva=_round(factura.iva_base * proporcion),
                retencion=Decimal("0.00"),
                total=_round(factura.total_base * proporcion),
            )
            if self._upsert(schema_name, "Nota de Débito", nota.numero_nota, nota.numero_control,
                             factura, nuevos, registrar_en_libro_compra_venta, dry_run):
                reconstruidas += 1

        # --- Huérfanas: cualquier línea activa que no corresponda a ningún documento real ---
        huerfanas_qs = LibroCompraVenta.objects.filter(activo=True).exclude(
            tipo_documento__in=["Factura", "Nota de Crédito", "Nota de Débito"]
        )
        # Unimos con las que sí son de esos tipos pero no están en `numeros_validos`.
        candidatas = LibroCompraVenta.objects.filter(
            activo=True, tipo_documento__in=["Factura", "Nota de Crédito", "Nota de Débito"],
        )
        ids_huerfanas = [
            l.id for l in candidatas
            if (l.tipo_documento, l.numero_documento) not in numeros_validos
        ]
        huerfanas = len(ids_huerfanas)
        if ids_huerfanas:
            for l in candidatas.filter(id__in=ids_huerfanas):
                self.stdout.write(
                    f"[{schema_name}] Huérfana: Libro #{l.id} ({l.tipo_documento} '{l.numero_documento}') -- sin documento fuente."
                )
            if not dry_run:
                LibroCompraVenta.objects.filter(id__in=ids_huerfanas).update(activo=False)

        return reconstruidas, huerfanas

    def _upsert(self, schema_name, tipo_documento, numero_documento, numero_control, factura, nuevos, registrar_fn, dry_run) -> bool:
        from apps.facturacion.models import LibroCompraVenta

        existente = LibroCompraVenta.objects.filter(
            tipo_documento=tipo_documento, numero_documento=numero_documento,
        ).first()
        if existente and existente.total == nuevos["total"] and existente.numero_control:
            return False

        self.stdout.write(
            f"[{schema_name}] {tipo_documento} {numero_documento}: "
            f"total Libro {existente.total if existente else '(sin línea)'} -> {nuevos['total']}"
        )
        if dry_run:
            return True

        razon_social = factura.cliente.nombre if factura.cliente else "Consumidor Final"
        rif = factura.cliente.documento if factura.cliente else None
        registrar_fn(
            tipo_libro="venta",
            fecha_operacion=factura.fecha_operacion.date(),
            tipo_documento=tipo_documento,
            numero_documento=numero_documento,
            numero_control=numero_control,
            rif=rif,
            razon_social=razon_social,
            **nuevos,
        )
        return True
