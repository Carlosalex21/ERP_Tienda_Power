# MVP: Administradoras de Condominios + Inmobiliarias

Un solo motor (app `inmuebles`), dos tipos de negocio con menú propio.

## 1. Cómo se ofrece

| | `condominios` (Administradora de Condominios) | `inmobiliaria` (Inmobiliaria) |
|---|---|---|
| Ve | Edificios, unidades, gastos comunes, recibos de condominio, cobranza, morosidad, solvencias | Propiedades, contratos, cobranza, morosidad, liquidaciones a propietarios, portal público |
| No ve | Contratos, liquidaciones | Edificios, gastos comunes |
| Comparte | Personas (Clientes), cobranza, recibos, morosidad, tasa de cambio, WhatsApp | igual |

Quien haga ambas cosas recibe los dos grupos de módulos mediante su plan (`Plan.modulos`).
La métrica de cobro natural es **unidades administradas** (`Plan.limite_unidades`).

Decisiones tomadas: cuotas y cánones se fijan en USD y se cobran en Bs a la tasa del día;
recibo interno (no fiscal) al cobrar, factura fiscal solo del honorario de la administradora;
liquidación al propietario incluida en el MVP (versión básica).

## 2. Modelo de datos (app `apps/inmuebles`)

Reutiliza: `clientes.Cliente` (propietarios, inquilinos, condóminos), `proveedores.Proveedor`
(gastos), `configuracion.TasaCambio/Moneda`, `facturacion.MetodoPago`, correlativos.

**Estructura**
- `Edificio`: nombre, dirección, RIF, día de vencimiento, % mora mensual, % fondo de reserva, datos bancarios para pagos.
- `Unidad`: edificio (opcional), código ("Apto 3-B"), tipo, alícuota %, m², propietario (Cliente),
  ocupante (Cliente), estado (ocupada / disponible / en alquiler / en venta), y datos comerciales
  (precio de venta, canon sugerido, habitaciones, baños, estacionamientos, descripción, fotos, publicada).

**Cobranza (motor compartido)**
- `Cargo`: unidad, pagador, tipo (cuota_condominio, canon, extraordinaria, fondo_reserva, multa, mora, otro),
  período `AAAA-MM`, monto USD, vencimiento, pagado USD, estado (pendiente / parcial / pagado / anulado),
  origen (período de condominio o contrato). Único por (origen, unidad, período): generar dos veces no duplica.
- `Recibo`: correlativo propio `REC-000001`, pagador, unidad, fecha, método, referencia, banco,
  moneda y monto recibido, **tasa aplicada**, equivalente USD, comprobante (subida validada), estado.
- `ReciboAplicacion`: recibo → cargo → monto USD (un pago puede saldar varios cargos, el más antiguo primero).

**Condominios**
- `GastoComun`: edificio, período, categoría, descripción, monto USD, proveedor, comprobante.
- `PeriodoCondominio`: edificio + período, estado (borrador / emitido), total gastos, fondo de reserva.
  Al **emitir** genera un `Cargo` por unidad = total × alícuota %.

**Inmobiliaria**
- `Contrato`: unidad, inquilino, fechas, canon USD, día de pago, depósito, honorario %, ajuste anual %,
  estado (borrador / vigente / vencido / rescindido), documento adjunto. Genera cargos mensuales.
- `GastoPropiedad`: reparaciones o mantenimiento a cargo del propietario.
- `Liquidacion`: propietario + período: canon cobrado − honorario % − gastos = **neto a transferir**.
  Estados borrador / pagada, con referencia de la transferencia.

## 3. Reglas clave

- Todo se guarda en USD; el pago guarda la tasa usada (nunca la de hoy después).
- Mora: al generar el período siguiente, cargo `mora` = % × saldo vencido (una vez por período, idempotente).
- Un recibo anulado revierte lo aplicado a sus cargos.
- Una unidad no puede tener dos contratos vigentes que se solapen.
- Un período de condominio emitido no se edita: se corrige con un cargo extraordinario o nota.
- Los comprobantes pasan por `validar_archivo_subido`.

## 4. Pantallas del MVP

**Condominios:** Edificios · Unidades (alta masiva por CSV) · Gastos comunes · Períodos y recibos
(vista previa de la distribución antes de emitir) · Cobranza (registrar pago → recibo PDF) ·
Morosidad (antigüedad por unidad + recordatorios por WhatsApp) · Certificado de solvencia (PDF).

**Inmobiliaria:** Propiedades (con filtros y estado) · Contratos (alta, renovación, por vencer) ·
Cobranza · Morosidad · Liquidaciones a propietarios (PDF) · Portal público de propiedades
con botón de WhatsApp.

**Compartido:** estado de cuenta por unidad con enlace firmado de solo lectura para enviar por WhatsApp;
tablero con cartera por cobrar, % de morosidad, cobrado del mes, unidades vacías y contratos por vencer (30/60/90 días).

## 5. Tareas automáticas (Celery)

1. Día 1 de cada mes: generar cargos de contratos vigentes (idempotente).
2. Diario: marcar cargos vencidos y contratos vencidos.
3. Diario: alertas de contratos por vencer (30/60/90 días) en el panel de alertas.

## 6. Cableado en el sistema (lo mismo que hicieron las demás verticales)

`TENANT_APPS` + `urls_tenants` + `Client.TIPO_NEGOCIO_CHOICES` (modelo, serializer, `tenant_service`) +
`tenants/modulos.py` (módulos facturables) + `modulosPanel.ts` (menú por tipo de negocio) +
`Plan.limite_unidades` + planes por tipo + demo sembrada por tipo (`seed_demo_tenant`).

## 7. Fuera del MVP (fase 2)

Portal del condómino/inquilino (ver deuda y reportar pago con comprobante) · pasarela de cobro ·
conciliación bancaria · fondo de reserva como libro aparte · asientos contables por edificio
(se apoya en `EmpresaContable`) · asambleas y votaciones · cartelera de avisos · comisiones de asesores ·
agenda de visitas · factura fiscal automática del honorario · contratos con plantilla.

## 8. Orden de construcción

| Fase | Contenido |
|---|---|
| A | Backend: modelos, servicios (distribución, cargos, recibos, mora, liquidación), API, pruebas |
| B | Frontend condominios + cobranza + morosidad + PDF de recibo |
| C | Frontend inmobiliaria: propiedades, contratos, liquidaciones, portal público |
| D | Tipos de negocio, planes, límite de unidades, demos sembradas, tablero y alertas |

## 9. Riesgos y pendientes

- Reglas legales de propiedad horizontal y arrendamientos varían por país: revisar con un abogado antes de
  prometer contratos o certificados con valor legal (el MVP genera documentos informativos).
- Validar con 5 administradoras o inmobiliarias antes de la fase C: cómo cobran hoy, cuántas unidades manejan y cuánto pagarían.
