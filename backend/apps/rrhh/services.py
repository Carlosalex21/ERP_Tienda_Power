"""Servicios de negocio de RRHH: generación y pago de nómina."""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import (
    Asistencia, ConceptoNomina, ConfiguracionRRHH, Horario, NominaEmpleado, NominaEmpleadoConcepto,
    PeriodoNomina, VacacionTomada,
)

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


def _dias_vacacion_en_rango(empleado, fecha_desde, fecha_hasta) -> list[date]:
    """
    Días calendario (dentro de [fecha_desde, fecha_hasta]) cubiertos por
    alguna `VacacionTomada` del empleado -- se usan para no descontarle esos
    días como ausencia al generar la nómina (ya están aprobados como
    vacaciones, no son una falta).
    """
    dias: list[date] = []
    tomadas = VacacionTomada.objects.filter(
        usuario=empleado, fecha_inicio__lte=fecha_hasta, fecha_fin__gte=fecha_desde,
    )
    for vacacion in tomadas:
        inicio = max(vacacion.fecha_inicio, fecha_desde)
        fin = min(vacacion.fecha_fin, fecha_hasta)
        dias.extend(date.fromordinal(o) for o in range(inicio.toordinal(), fin.toordinal() + 1))
    return dias


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
        ).exclude(fecha__in=_dias_vacacion_en_rango(empleado, fecha_desde, fecha_hasta)).count()
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

        _aplicar_conceptos_recurrentes(nomina_empleado, sueldo_base)
        _recalcular_totales(nomina_empleado)

    return periodo


def _recalcular_totales(nomina_empleado: NominaEmpleado) -> None:
    """
    Recalcula bonificaciones/otras_deducciones/total_pagar de una línea a
    partir de TODOS sus `NominaEmpleadoConcepto` actuales (recurrentes +
    puntuales) -- se llama tanto al generar el período como al agregar o
    quitar un concepto manual después (ver `agregar_concepto_manual`).
    """
    conceptos = nomina_empleado.conceptos.all()
    total_bonos = _round(sum((c.monto for c in conceptos if c.tipo == 'bono'), Decimal('0')))
    total_deducciones = _round(sum((c.monto for c in conceptos if c.tipo == 'deduccion'), Decimal('0')))
    total = _round(
        nomina_empleado.sueldo_base - nomina_empleado.deduccion_ausencias + nomina_empleado.pago_horas_extra
        + total_bonos - total_deducciones,
    )
    nomina_empleado.bonificaciones = total_bonos
    nomina_empleado.otras_deducciones = total_deducciones
    nomina_empleado.total_pagar = total
    nomina_empleado.save(update_fields=['bonificaciones', 'otras_deducciones', 'total_pagar'])


@transaction.atomic
def agregar_concepto_manual(nomina_empleado: NominaEmpleado, *, nombre: str, tipo: str, monto: Decimal) -> NominaEmpleado:
    """
    Agrega un concepto puntual (ej. una comisión de ventas del mes, que varía
    por empleado y no es un % o monto fijo recurrente para todos -- ver
    `ConceptoNomina`) a UNA línea de nómina ya generada, mientras su período
    siga en borrador. No crea un `ConceptoNomina` reutilizable: es exclusivo
    de este período/empleado, igual que el resto de la línea es un snapshot.
    """
    if nomina_empleado.periodo.estado != 'borrador':
        raise NominaError('Solo se pueden agregar conceptos a un período todavía en borrador.')
    if tipo not in dict(ConceptoNomina.TIPO_CHOICES):
        raise NominaError('Tipo de concepto inválido.')
    monto = _round(monto)
    if monto <= 0:
        raise NominaError('El monto debe ser mayor a 0.')

    NominaEmpleadoConcepto.objects.create(
        nomina_empleado=nomina_empleado, concepto=None, nombre=nombre, tipo=tipo, monto=monto,
    )
    _recalcular_totales(nomina_empleado)
    return nomina_empleado


@transaction.atomic
def quitar_concepto_manual(concepto_aplicado: NominaEmpleadoConcepto) -> NominaEmpleado:
    """Inversa de `agregar_concepto_manual` -- no permite tocar uno que venga de un `ConceptoNomina` recurrente (ese se desactiva desde Bonos y Deducciones, no se borra línea por línea)."""
    nomina_empleado = concepto_aplicado.nomina_empleado
    if nomina_empleado.periodo.estado != 'borrador':
        raise NominaError('Solo se pueden quitar conceptos de un período todavía en borrador.')
    if concepto_aplicado.concepto_id is not None:
        raise NominaError('Este concepto viene de una configuración recurrente -- desactívalo desde Bonos y Deducciones.')
    concepto_aplicado.delete()
    _recalcular_totales(nomina_empleado)
    return nomina_empleado


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


# --- Vacaciones y liquidación ---------------------------------------------
# Deliberadamente sin tasas legales hardcodeadas (ver `ConfiguracionRRHH`):
# el sistema calcula sobre los parámetros (días/año, días que representa el
# sueldo base) que el propio tenant o su contador configuran una vez.

def obtener_configuracion_rrhh() -> ConfiguracionRRHH:
    config, _ = ConfiguracionRRHH.objects.get_or_create(pk=1)
    return config


def calcular_antiguedad_anios(fecha_contratacion, hasta=None) -> Decimal:
    """Años completos (con decimales) entre `fecha_contratacion` y `hasta` (hoy si no se indica)."""
    hasta = hasta or timezone.localdate()
    dias = (hasta - fecha_contratacion).days
    if dias <= 0:
        return Decimal('0')
    return (Decimal(dias) / Decimal('365.25')).quantize(Decimal('0.01'))


def calcular_vacaciones(empleado) -> dict:
    """
    Días de vacaciones acumulados por antigüedad, cuántos ya se registraron
    como tomados (ver `VacacionTomada`) y el saldo disponible. Sin
    `fecha_contratacion` cargada no hay antigüedad que calcular -- devuelve
    todo en 0 en vez de asumir una fecha de ingreso.
    """
    config = obtener_configuracion_rrhh()
    metadata = empleado.metadata
    if not metadata.fecha_contratacion:
        return {
            'antiguedad_anios': Decimal('0'), 'dias_acumulados': 0,
            'dias_tomados': 0, 'dias_disponibles': 0,
        }

    antiguedad_anios = calcular_antiguedad_anios(metadata.fecha_contratacion)
    dias_acumulados = int(antiguedad_anios * config.dias_vacaciones_por_anio)
    dias_tomados = sum(
        (v.dias for v in VacacionTomada.objects.filter(usuario=empleado)), 0,
    )
    return {
        'antiguedad_anios': antiguedad_anios,
        'dias_acumulados': dias_acumulados,
        'dias_tomados': dias_tomados,
        'dias_disponibles': dias_acumulados - dias_tomados,
    }


@transaction.atomic
def registrar_vacacion_tomada(
    empleado, *, fecha_inicio, fecha_fin, observaciones: str = '', registrado_por=None,
) -> VacacionTomada:
    """
    Registra un período de vacaciones ya tomado -- no bloquea si deja el
    saldo en negativo (puede haber acuerdos particulares con el empleado);
    el saldo negativo queda visible en `calcular_vacaciones` para que el
    admin lo vea, no lo impide.
    """
    if fecha_inicio > fecha_fin:
        raise NominaError('La fecha de inicio no puede ser posterior a la fecha de fin.')
    dias = (fecha_fin - fecha_inicio).days + 1
    return VacacionTomada.objects.create(
        usuario=empleado, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        dias=dias, observaciones=observaciones, registrado_por=registrado_por,
    )


def eliminar_vacacion_tomada(vacacion: VacacionTomada) -> None:
    vacacion.delete()


def calcular_liquidacion(empleado, fecha_egreso) -> dict:
    """
    Calculadora de referencia para la liquidación de un empleado al terminar
    la relación laboral -- NO crea ningún registro ni paga nada, es solo un
    desglose para que el admin/contador lo revise (y ajuste según su
    legislación específica) antes de procesar el pago real por fuera del
    sistema o como un concepto manual en la próxima nómina.
    """
    metadata = empleado.metadata
    if not metadata.fecha_contratacion:
        raise NominaError('El empleado no tiene fecha de contratación registrada -- no se puede calcular su antigüedad.')
    if not metadata.sueldo_base:
        raise NominaError('El empleado no tiene un sueldo base asignado.')
    if fecha_egreso < metadata.fecha_contratacion:
        raise NominaError('La fecha de egreso no puede ser anterior a la fecha de contratación.')

    config = obtener_configuracion_rrhh()
    sueldo_diario = _round(metadata.sueldo_base / Decimal(config.dias_periodo_sueldo_base))
    antiguedad_anios = calcular_antiguedad_anios(metadata.fecha_contratacion, hasta=fecha_egreso)

    vacaciones = calcular_vacaciones(empleado)
    dias_vacaciones_pendientes = max(vacaciones['dias_disponibles'], 0)
    monto_vacaciones = _round(sueldo_diario * dias_vacaciones_pendientes)

    dias_prestaciones = int(antiguedad_anios * config.dias_prestaciones_por_anio)
    monto_prestaciones = _round(sueldo_diario * dias_prestaciones)

    total = _round(monto_vacaciones + monto_prestaciones)
    return {
        'antiguedad_anios': antiguedad_anios,
        'sueldo_diario': sueldo_diario,
        'dias_vacaciones_pendientes': dias_vacaciones_pendientes,
        'monto_vacaciones_pendientes': monto_vacaciones,
        'dias_prestaciones_acumulados': dias_prestaciones,
        'monto_prestaciones': monto_prestaciones,
        'total_liquidacion': total,
    }
