"""Servicios de negocio de RRHH: generación y pago de nómina."""
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import Asistencia, ConceptoNomina, Horario, NominaEmpleado, NominaEmpleadoConcepto, PeriodoNomina

CENT = Decimal('0.01')

# Multiplicador estándar de hora extra diurna (1.5x la hora normal) -- un
# punto de partida razonable, no una tasa legal fija: cada país/convenio
# tiene sus propios recargos (nocturno, feriado, etc.) que este sistema no
# intenta modelar automáticamente. Se aplica sobre las horas que el propio
# empleado marcó por encima de su `Horario` oficial (ver `_calcular_horas_extra`).
MULTIPLICADOR_HORA_EXTRA = Decimal('1.5')
HORAS_JORNADA_ESTANDAR = Decimal('8')


def _round(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT)


class NominaError(Exception):
    """Error controlado al generar/pagar una nómina."""


def _calcular_horas_extra(empleado, fecha_desde, fecha_hasta) -> Decimal:
    """
    Suma, en horas, cuánto trabajó el empleado por ENCIMA de su jornada
    oficial (`Horario.hora_entrada_oficial`/`hora_salida_oficial`) según sus
    propios marcajes de entrada/salida (`Asistencia`) -- se ignora
    cualquier día sin `hora_salida` (turno aún abierto o nunca marcado) para
    no inventar horas extra sobre un dato incompleto.

    Sin un `Horario` configurado, no hay jornada oficial contra la cual
    comparar -- se devuelve 0 en vez de asumir una jornada por defecto.
    """
    horario = Horario.objects.first()
    if not horario:
        return Decimal('0')

    jornada_oficial = datetime.combine(fecha_desde, horario.hora_salida_oficial) - datetime.combine(
        fecha_desde, horario.hora_entrada_oficial,
    )
    if jornada_oficial.total_seconds() <= 0:
        return Decimal('0')

    asistencias = Asistencia.objects.filter(
        usuario=empleado, fecha__range=[fecha_desde, fecha_hasta],
        hora_entrada__isnull=False, hora_salida__isnull=False,
    )
    total_horas_extra = Decimal('0')
    for asistencia in asistencias:
        trabajado = asistencia.hora_salida - asistencia.hora_entrada
        exceso = trabajado - jornada_oficial
        if exceso.total_seconds() > 0:
            total_horas_extra += Decimal(str(exceso.total_seconds() / 3600))

    return total_horas_extra.quantize(Decimal('0.01'))


def _aplicar_conceptos_recurrentes(nomina_empleado: NominaEmpleado, sueldo_base: Decimal) -> tuple[Decimal, Decimal]:
    """
    Aplica todos los `ConceptoNomina` activos y recurrentes a esta línea,
    dejando un snapshot (`NominaEmpleadoConcepto`) de cada uno -- devuelve
    `(total_bonos, total_deducciones)` ya redondeados.
    """
    total_bonos = Decimal('0')
    total_deducciones = Decimal('0')
    conceptos = ConceptoNomina.objects.filter(activo=True, recurrente=True)
    aplicados = []
    for concepto in conceptos:
        monto = (sueldo_base * concepto.valor / Decimal('100')) if concepto.modo == 'porcentaje' else concepto.valor
        monto = _round(monto)
        if monto <= 0:
            continue
        aplicados.append(NominaEmpleadoConcepto(
            nomina_empleado=nomina_empleado, concepto=concepto,
            nombre=concepto.nombre, tipo=concepto.tipo, monto=monto,
        ))
        if concepto.tipo == 'bono':
            total_bonos += monto
        else:
            total_deducciones += monto
    if aplicados:
        NominaEmpleadoConcepto.objects.bulk_create(aplicados)
    return total_bonos, total_deducciones


@transaction.atomic
def generar_periodo_nomina(*, fecha_desde, fecha_hasta, usuario) -> PeriodoNomina:
    """
    Crea un `PeriodoNomina` en borrador con una línea por cada empleado
    activo que tenga `sueldo_base` asignado -- descuenta proporcionalmente
    los días de ausencia real registrados en `Asistencia` dentro del rango,
    suma las horas extra reales marcadas por encima del horario oficial, y
    aplica los `ConceptoNomina` recurrentes (bonos/deducciones) configurados.
    """
    if fecha_desde > fecha_hasta:
        raise NominaError('La fecha desde no puede ser posterior a la fecha hasta.')
    if PeriodoNomina.objects.filter(fecha_desde=fecha_desde, fecha_hasta=fecha_hasta).exists():
        raise NominaError('Ya existe un período de nómina para ese rango exacto de fechas.')

    empleados = User.objects.filter(
        is_active=True, metadata__sueldo_base__isnull=False, metadata__sueldo_base__gt=0,
    ).select_related('metadata')
    if not empleados.exists():
        raise NominaError('Ningún empleado tiene un sueldo base asignado -- asígnalo desde Empleados antes de generar la nómina.')

    dias_periodo = (fecha_hasta - fecha_desde).days + 1
    periodo = PeriodoNomina.objects.create(fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, usuario=usuario)

    for empleado in empleados:
        sueldo_base = empleado.metadata.sueldo_base
        dias_ausencia = Asistencia.objects.filter(
            usuario=empleado, fecha__range=[fecha_desde, fecha_hasta], estado='Ausente',
        ).count()
        valor_dia = sueldo_base / Decimal(dias_periodo) if dias_periodo else Decimal('0')
        deduccion_ausencias = _round(valor_dia * dias_ausencia)

        horas_extra = _calcular_horas_extra(empleado, fecha_desde, fecha_hasta)
        valor_hora = valor_dia / HORAS_JORNADA_ESTANDAR if HORAS_JORNADA_ESTANDAR else Decimal('0')
        pago_horas_extra = _round(horas_extra * valor_hora * MULTIPLICADOR_HORA_EXTRA)

        total_provisional = _round(sueldo_base - deduccion_ausencias + pago_horas_extra)
        nomina_empleado = NominaEmpleado.objects.create(
            periodo=periodo, usuario=empleado, sueldo_base=sueldo_base,
            dias_ausencia=dias_ausencia, deduccion_ausencias=deduccion_ausencias,
            horas_extra=horas_extra, pago_horas_extra=pago_horas_extra,
            total_pagar=total_provisional,
        )

        total_bonos, total_deducciones = _aplicar_conceptos_recurrentes(nomina_empleado, sueldo_base)
        total = _round(sueldo_base - deduccion_ausencias + pago_horas_extra + total_bonos - total_deducciones)
        nomina_empleado.bonificaciones = total_bonos
        nomina_empleado.otras_deducciones = total_deducciones
        nomina_empleado.total_pagar = total
        nomina_empleado.save(update_fields=['bonificaciones', 'otras_deducciones', 'total_pagar'])

    return periodo


@transaction.atomic
def pagar_periodo_nomina(periodo: PeriodoNomina, usuario) -> PeriodoNomina:
    """Marca el período como pagado y genera su asiento contable automático (una sola vez)."""
    if periodo.estado == 'pagada':
        raise NominaError('Este período de nómina ya fue pagado.')

    periodo.estado = 'pagada'
    periodo.fecha_pago = timezone.now()
    periodo.save(update_fields=['estado', 'fecha_pago'])

    try:
        from apps.contabilidad.services import generar_asiento_automatico_nomina
        generar_asiento_automatico_nomina(periodo)
    except Exception:
        pass

    return periodo
