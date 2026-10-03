"""API del panel de inmuebles (condominios e inmobiliaria)."""
import csv
import io
import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clientes.models import Cliente
from apps.core.plan_limits import verificar_limite
from apps.core.uploads import validar_archivo_subido
from apps.inmuebles.api import serializers as sz
from apps.inmuebles.api.permissions import EsPersonal, PermisosPorAccion
from apps.inmuebles.models import (
    Cargo, ConsultaPropiedad, Contrato, Edificio, GastoComun, GastoPropiedad, Liquidacion, MedioPago, PagoReportado,
    PeriodoCondominio, Recibo, Unidad, UnidadFoto,
)
from apps.inmuebles.services import cobranza, condominio, contratos, liquidaciones, pdf, portal, reportes
from apps.inmuebles.services.cobranza import CobranzaError


def _error(exc: Exception) -> serializers.ValidationError:
    return serializers.ValidationError({'detail': str(exc)})


def _pdf(contenido: bytes, nombre: str, request) -> HttpResponse:
    respuesta = HttpResponse(contenido, content_type='application/pdf')
    disposicion = 'attachment' if request.query_params.get('download') == '1' else 'inline'
    respuesta['Content-Disposition'] = f'{disposicion}; filename="{nombre}.pdf"'
    return respuesta


class VistaConErrores:
    """Convierte los errores controlados del negocio en respuestas 400 con mensaje claro."""

    def handle_exception(self, exc):
        if isinstance(exc, CobranzaError):
            exc = _error(exc)
        return super().handle_exception(exc)


# --- Estructura ---------------------------------------------------------------

class EdificioViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    serializer_class = sz.EdificioSerializer
    filterset_fields = ['activo']
    search_fields = ['nombre', 'rif', 'direccion']

    def get_queryset(self):
        return Edificio.objects.annotate(unidades_activas=Count('unidades', filter=Q(unidades__activo=True)))

    def perform_destroy(self, instance):
        if instance.unidades.filter(activo=True).exists():
            raise serializers.ValidationError({'detail': 'El edificio tiene unidades activas: desactívalas o muévelas antes.'})
        instance.activo = False
        instance.save(update_fields=['activo'])


class UnidadViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    """Se registra bajo dos rutas (`unidades` y `propiedades`) para poder vender cada módulo por separado."""
    serializer_class = sz.UnidadSerializer
    filterset_fields = ['edificio', 'estado', 'tipo', 'operacion', 'publicada', 'propietario', 'ocupante', 'activo']
    search_fields = ['codigo', 'titulo', 'zona', 'direccion', 'propietario__nombre', 'ocupante__nombre']
    ordering_fields = ['codigo', 'fecha_creacion', 'canon_usd', 'precio_venta_usd']

    def get_queryset(self):
        return Unidad.objects.select_related('edificio', 'propietario', 'ocupante').prefetch_related(
            'fotos', Prefetch('cargos', queryset=Cargo.objects.filter(estado='pendiente'), to_attr='cargos_pendientes'),
        )

    def perform_create(self, serializer):
        verificar_limite(self.request, 'limite_unidades', Unidad.objects.filter(activo=True).count(), 'unidades o propiedades')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.cargos.filter(estado='pendiente').exists():
            raise serializers.ValidationError({'detail': 'La unidad tiene deudas pendientes. Cóbralas o anúlalas antes de desactivarla.'})
        if instance.contratos.filter(estado='vigente').exists():
            raise serializers.ValidationError({'detail': 'La propiedad tiene un contrato vigente. Rescíndelo antes de desactivarla.'})
        instance.activo = False
        instance.publicada = False
        instance.save(update_fields=['activo', 'publicada'])

    @action(detail=True, methods=['post'], url_path='fotos', parser_classes=[MultiPartParser, FormParser])
    def agregar_foto(self, request, pk=None):
        unidad = self.get_object()
        archivo = validar_archivo_subido(request.FILES.get('imagen'), max_mb=8, campo='imagen')
        # Consultas directas (no `unidad.fotos`): el queryset del viewset precarga las fotos y eso devolvería datos viejos.
        fotos = UnidadFoto.objects.filter(unidad=unidad)
        if fotos.count() >= 20:
            raise serializers.ValidationError({'imagen': 'Cada propiedad admite hasta 20 fotos.'})
        portada = request.data.get('es_portada') in ('1', 'true', 'True', True) or not fotos.exists()
        if portada:
            fotos.update(es_portada=False)
        foto = UnidadFoto.objects.create(unidad=unidad, imagen=archivo, es_portada=portada, orden=fotos.count())
        return Response(sz.UnidadFotoSerializer(foto, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post', 'delete'], url_path=r'fotos/(?P<foto_id>\d+)')
    def foto(self, request, pk=None, foto_id=None):
        unidad = self.get_object()
        foto = UnidadFoto.objects.filter(unidad=unidad, pk=foto_id).first()
        if foto is None:
            return Response({'detail': 'Foto no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if request.method == 'DELETE':
            era_portada = foto.es_portada
            foto.imagen.delete(save=False)
            foto.delete()
            if era_portada:
                siguiente = UnidadFoto.objects.filter(unidad=unidad).first()
                if siguiente:
                    siguiente.es_portada = True
                    siguiente.save(update_fields=['es_portada'])
            return Response(status=status.HTTP_204_NO_CONTENT)
        UnidadFoto.objects.filter(unidad=unidad).update(es_portada=False)  # POST = marcar como portada
        foto.es_portada = True
        foto.save(update_fields=['es_portada'])
        return Response(sz.UnidadFotoSerializer(foto, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='estado-cuenta')
    def estado_cuenta(self, request, pk=None):
        return Response(reportes.estado_cuenta(self.get_object()))

    @action(detail=True, methods=['get'], url_path='estado-cuenta-pdf')
    def estado_cuenta_pdf(self, request, pk=None):
        unidad = self.get_object()
        return _pdf(pdf.pdf_estado_cuenta(unidad), f'estado_cuenta_{unidad.codigo}', request)

    @action(detail=True, methods=['get'], url_path='solvencia-pdf')
    def solvencia_pdf(self, request, pk=None):
        unidad = self.get_object()
        return _pdf(pdf.pdf_solvencia(unidad), f'solvencia_{unidad.codigo}', request)

    @action(detail=False, methods=['get'], url_path='plantilla-csv')
    def plantilla_csv(self, request):
        contenido = (
            'codigo,tipo,alicuota,area_m2,propietario_nombre,propietario_documento,propietario_telefono,propietario_email\r\n'
            'Apto 1-A,apartamento,2.5000,85,María González,V-12345678,0414-1234567,maria@correo.com\r\n'
        )
        respuesta = HttpResponse(contenido, content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition'] = 'attachment; filename="plantilla_unidades.csv"'
        return respuesta

    @action(detail=False, methods=['post'], url_path='importar', parser_classes=[MultiPartParser, FormParser])
    def importar(self, request):
        """Alta masiva de unidades (y sus propietarios) desde un CSV -- el arranque de una administradora con decenas de unidades."""
        archivo = request.FILES.get('archivo')
        if archivo is None or not archivo.name.lower().endswith('.csv'):
            raise serializers.ValidationError({'archivo': 'Sube un archivo .csv (descarga la plantilla).'})
        if archivo.size > 2 * 1024 * 1024:
            raise serializers.ValidationError({'archivo': 'El archivo es muy pesado (máximo 2 MB).'})
        edificio = None
        if request.data.get('edificio'):
            edificio = Edificio.objects.filter(pk=request.data['edificio']).first()
            if edificio is None:
                raise serializers.ValidationError({'edificio': 'Edificio no encontrado.'})
        try:
            texto = archivo.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            raise serializers.ValidationError({'archivo': 'El archivo debe estar guardado como CSV UTF-8.'})
        primera = texto.splitlines()[0] if texto.strip() else ''
        lector = csv.DictReader(io.StringIO(texto), delimiter=';' if primera.count(';') > primera.count(',') else ',')
        filas = list(lector)
        if not filas:
            raise serializers.ValidationError({'archivo': 'El archivo no tiene filas.'})
        if len(filas) > 1000:
            raise serializers.ValidationError({'archivo': 'Máximo 1000 filas por archivo.'})

        tipos = {self._norm(v): k for k, v in Unidad.TIPO_CHOICES} | {self._norm(k): k for k, _ in Unidad.TIPO_CHOICES}
        creadas, errores = 0, []
        for numero, fila in enumerate(filas, start=2):
            fila = {self._norm(k or ''): (v or '').strip() for k, v in fila.items()}
            codigo = fila.get('codigo', '')
            try:
                if not codigo:
                    raise ValueError('Falta el código de la unidad.')
                try:
                    alicuota = Decimal((fila.get('alicuota') or '0').replace(',', '.'))
                    area = Decimal((fila.get('area_m2') or '').replace(',', '.')) if fila.get('area_m2') else None
                except InvalidOperation:
                    raise ValueError('La alícuota o el área no es un número válido.')
                if not (0 <= alicuota <= 100):
                    raise ValueError('La alícuota debe estar entre 0 y 100.')
                if Unidad.objects.filter(edificio=edificio, codigo__iexact=codigo).exists():
                    raise ValueError(f'Ya existe la unidad "{codigo}".')
                verificar_limite(request, 'limite_unidades', Unidad.objects.filter(activo=True).count(), 'unidades o propiedades')
                with transaction.atomic():
                    Unidad.objects.create(
                        edificio=edificio, codigo=codigo, tipo=tipos.get(self._norm(fila.get('tipo', '')), 'apartamento'),
                        alicuota=alicuota, area_m2=area, propietario=self._propietario(fila),
                    )
                creadas += 1
            except Exception as exc:
                detalle = exc.detail if hasattr(exc, 'detail') else str(exc)
                errores.append({'fila': numero, 'codigo': codigo, 'error': str(detalle)})
                if 'plan' in str(detalle).lower():
                    break
        return Response({'creadas': creadas, 'con_error': len(errores), 'errores': errores[:50]})

    @staticmethod
    def _norm(texto: str) -> str:
        sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        return sin_acentos.strip().lower().replace(' ', '_')

    @staticmethod
    def _propietario(fila):
        nombre, documento = fila.get('propietario_nombre', ''), fila.get('propietario_documento', '')
        if not nombre and not documento:
            return None
        cliente = Cliente.objects.filter(documento=documento).first() if documento else None
        if cliente is None and nombre:
            cliente = Cliente.objects.filter(nombre__iexact=nombre, documento__in=[None, '']).first() if not documento else None
        if cliente is None:
            datos = {'nombre': nombre or documento, 'documento': documento or None}
            telefono, email = fila.get('propietario_telefono') or None, fila.get('propietario_email') or None
            try:
                with transaction.atomic():
                    cliente = Cliente.objects.create(**datos, telefono=telefono, email=email)
            except IntegrityError:  # teléfono o correo ya usado por otra persona
                cliente = Cliente.objects.create(**datos)
        return cliente


class MedioPagoViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    serializer_class = sz.MedioPagoSerializer
    filterset_fields = ['edificio', 'tipo', 'activo']

    def get_queryset(self):
        return MedioPago.objects.select_related('edificio')


# --- Condominios --------------------------------------------------------------

class GastoComunViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    serializer_class = sz.GastoComunSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ['edificio', 'periodo', 'categoria']
    search_fields = ['descripcion', 'proveedor__nombre']

    def get_queryset(self):
        return GastoComun.objects.select_related('edificio', 'proveedor')

    def perform_create(self, serializer):
        condominio.validar_gasto_editable(serializer.validated_data['edificio'], serializer.validated_data['periodo'])
        serializer.save(usuario=self.request.user)

    def perform_update(self, serializer):
        condominio.validar_gasto_editable(serializer.instance.edificio, serializer.instance.periodo)
        nuevo = serializer.validated_data
        condominio.validar_gasto_editable(nuevo.get('edificio', serializer.instance.edificio), nuevo.get('periodo', serializer.instance.periodo))
        serializer.save()

    def perform_destroy(self, instance):
        condominio.validar_gasto_editable(instance.edificio, instance.periodo)
        instance.delete()


class PeriodoCondominioViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.PeriodoCondominioSerializer
    filterset_fields = ['edificio', 'periodo', 'estado']
    acciones_admin = ('anular', 'emitir')

    def get_queryset(self):
        return PeriodoCondominio.objects.select_related('edificio')

    def _edificio_y_periodo(self, request):
        datos = request.data if request.method == 'POST' else request.query_params
        edificio = Edificio.objects.filter(pk=datos.get('edificio')).first()
        if edificio is None:
            raise serializers.ValidationError({'edificio': 'Selecciona un edificio.'})
        return edificio, datos.get('periodo', '')

    @action(detail=False, methods=['get'])
    def previsualizar(self, request):
        edificio, periodo = self._edificio_y_periodo(request)
        return Response(condominio.previsualizar_periodo(edificio, periodo))

    @action(detail=False, methods=['post'])
    def emitir(self, request):
        edificio, periodo = self._edificio_y_periodo(request)
        vencimiento = request.data.get('fecha_vencimiento') or None
        if vencimiento:
            vencimiento = serializers.DateField().to_internal_value(vencimiento)
        emitido = condominio.emitir_periodo(
            edificio, periodo, usuario=request.user, fecha_vencimiento=vencimiento,
            forzar_alicuotas=bool(request.data.get('forzar_alicuotas')),
        )
        return Response(self.get_serializer(emitido).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        return Response(self.get_serializer(condominio.anular_periodo(self.get_object())).data)


# --- Cobranza -----------------------------------------------------------------

class CargoViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.CargoSerializer
    filterset_fields = ['unidad', 'estado', 'tipo', 'periodo', 'unidad__edificio', 'pagador', 'contrato']
    search_fields = ['concepto', 'unidad__codigo', 'pagador__nombre']
    ordering_fields = ['fecha_vencimiento', 'monto_usd', 'periodo']
    acciones_admin = ('anular',)

    def get_queryset(self):
        qs = Cargo.objects.select_related('unidad__edificio', 'pagador')
        parametros = self.request.query_params
        if parametros.get('vencido') in ('1', 'true'):
            qs = qs.filter(estado='pendiente', fecha_vencimiento__lt=timezone.localdate())
        return qs

    def create(self, request, *args, **kwargs):
        datos = sz.CrearCargoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        v = datos.validated_data
        cargo = cobranza.crear_cargo(
            unidad=v['unidad'], tipo=v['tipo'], concepto=v['concepto'], periodo=v['periodo'], monto_usd=v['monto_usd'],
            fecha_vencimiento=v['fecha_vencimiento'],
        )
        cobranza.aplicar_creditos(v['unidad'])
        cargo.refresh_from_db()
        return Response(self.get_serializer(cargo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        return Response(self.get_serializer(cobranza.anular_cargo(self.get_object())).data)

    @action(detail=True, methods=['get'], url_path='recibo-condominio-pdf')
    def recibo_condominio_pdf(self, request, pk=None):
        cargo = self.get_object()
        return _pdf(pdf.pdf_recibo_condominio(cargo), f'recibo_condominio_{cargo.unidad.codigo}_{cargo.periodo}', request)


class ReciboViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.ReciboSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ['unidad', 'estado', 'metodo', 'pagador', 'unidad__edificio']
    search_fields = ['numero', 'referencia', 'unidad__codigo', 'pagador__nombre']
    ordering_fields = ['fecha', 'monto_usd', 'numero']
    acciones_admin = ('anular',)

    def get_queryset(self):
        qs = Recibo.objects.select_related('unidad__edificio', 'pagador').prefetch_related('aplicaciones__cargo')
        parametros = self.request.query_params
        if parametros.get('desde'):
            qs = qs.filter(fecha__gte=parametros['desde'])
        if parametros.get('hasta'):
            qs = qs.filter(fecha__lte=parametros['hasta'])
        return qs

    def create(self, request, *args, **kwargs):
        datos = sz.RegistrarReciboSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        v = datos.validated_data
        recibo = cobranza.registrar_recibo(
            usuario=request.user, unidad=v['unidad'], fecha=v['fecha'], monto_pago=v['monto_pago'], moneda_pago=v['moneda_pago'],
            tasa=v.get('tasa'), metodo=v['metodo'], referencia=v['referencia'], banco=v['banco'], cargos=v.get('cargos') or None,
            comprobante=v.get('comprobante'), observaciones=v['observaciones'],
        )
        return Response(self.get_serializer(recibo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        recibo = cobranza.anular_recibo(self.get_object(), motivo=request.data.get('motivo', ''))
        return Response(self.get_serializer(recibo).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        recibo = self.get_object()
        return _pdf(pdf.pdf_recibo(recibo), recibo.numero, request)


class PagoReportadoViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.PagoReportadoSerializer
    filterset_fields = ['estado', 'unidad', 'cliente', 'unidad__edificio']
    search_fields = ['referencia', 'unidad__codigo', 'cliente__nombre']

    def get_queryset(self):
        return PagoReportado.objects.select_related('unidad__edificio', 'cliente', 'recibo').prefetch_related('cargos')

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        datos = sz.AprobarPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        v = datos.validated_data
        pago = portal.aprobar_pago_reportado(
            self.get_object(), usuario=request.user, tasa=v.get('tasa'), monto_pago=v.get('monto_pago'), observaciones=v['observaciones'],
        )
        return Response(self.get_serializer(pago).data)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        datos = sz.RechazarPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        pago = portal.rechazar_pago_reportado(self.get_object(), usuario=request.user, motivo=datos.validated_data['motivo'])
        return Response(self.get_serializer(pago).data)


class PortalAccesoView(VistaConErrores, APIView):
    """Genera, regenera o revoca el enlace del portal de una persona."""
    permission_classes = [EsPersonal]

    def _cliente(self, request):
        cliente = Cliente.objects.filter(pk=request.data.get('cliente') or request.query_params.get('cliente')).first()
        if cliente is None:
            raise serializers.ValidationError({'cliente': 'Selecciona una persona.'})
        return cliente

    def get(self, request):
        cliente = self._cliente(request)
        acceso = portal.obtener_o_crear_acceso(cliente)
        return Response({'token': acceso.token, 'cliente': cliente.pk, 'nombre': cliente.nombre, 'telefono': cliente.telefono})

    def post(self, request):
        cliente = self._cliente(request)
        acceso = portal.regenerar_acceso(cliente) if request.data.get('regenerar') else portal.obtener_o_crear_acceso(cliente)
        return Response({'token': acceso.token, 'cliente': cliente.pk, 'nombre': cliente.nombre, 'telefono': cliente.telefono})

    def delete(self, request):
        revocados = portal.revocar_accesos(self._cliente(request))
        return Response({'revocados': revocados})


# --- Inmobiliaria -------------------------------------------------------------

class ContratoViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    serializer_class = sz.ContratoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ['estado', 'unidad', 'inquilino', 'propietario']
    search_fields = ['unidad__codigo', 'unidad__titulo', 'inquilino__nombre', 'propietario__nombre']
    ordering_fields = ['fecha_inicio', 'fecha_fin', 'canon_usd']
    acciones_admin = ('destroy',)

    def get_queryset(self):
        qs = Contrato.objects.select_related('unidad__edificio', 'inquilino', 'propietario')
        dias = self.request.query_params.get('por_vencer')
        if dias and dias.isdigit():
            hoy = timezone.localdate()
            qs = qs.filter(estado='vigente', fecha_fin__gte=hoy, fecha_fin__lte=hoy + timedelta(days=int(dias)))
        return qs

    def create(self, request, *args, **kwargs):
        datos = self.get_serializer(data=request.data)
        datos.is_valid(raise_exception=True)
        v = datos.validated_data
        contrato = contratos.crear_contrato(
            usuario=request.user, unidad=v['unidad'], inquilino=v['inquilino'], fecha_inicio=v['fecha_inicio'], fecha_fin=v['fecha_fin'],
            canon_usd=v['canon_usd'], dia_pago=v.get('dia_pago', 5), deposito_usd=v.get('deposito_usd', 0),
            honorario_pct=v.get('honorario_pct', 0), ajuste_anual_pct=v.get('ajuste_anual_pct', 0),
            mora_pct_mensual=v.get('mora_pct_mensual', 0), dias_gracia=v.get('dias_gracia', 0), documento=v.get('documento'),
            observaciones=v.get('observaciones', ''),
        )
        return Response(self.get_serializer(contrato).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if self.get_object().estado != 'borrador':
            raise serializers.ValidationError({'detail': 'Solo un contrato en borrador se puede editar. Para cambios usa renovar o rescindir.'})
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        contrato = self.get_object()
        if contrato.estado != 'borrador':
            raise serializers.ValidationError({'detail': 'Solo se puede eliminar un contrato en borrador.'})
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def activar(self, request, pk=None):
        activo = contratos.activar_contrato(self.get_object(), cobrar_deposito=request.data.get('cobrar_deposito', True) not in (False, 'false', '0'))
        return Response(self.get_serializer(activo).data)

    @action(detail=True, methods=['post'])
    def rescindir(self, request, pk=None):
        datos = sz.RescindirContratoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        contrato = contratos.rescindir_contrato(self.get_object(), fecha=datos.validated_data.get('fecha'), motivo=datos.validated_data['motivo'])
        return Response(self.get_serializer(contrato).data)

    @action(detail=True, methods=['post'])
    def renovar(self, request, pk=None):
        datos = sz.RenovarContratoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        nuevo = contratos.renovar_contrato(
            self.get_object(), usuario=request.user, nueva_fecha_fin=datos.validated_data['nueva_fecha_fin'], nuevo_canon=datos.validated_data.get('nuevo_canon'),
        )
        return Response(self.get_serializer(nuevo).data, status=status.HTTP_201_CREATED)


class GastoPropiedadViewSet(VistaConErrores, PermisosPorAccion, viewsets.ModelViewSet):
    serializer_class = sz.GastoPropiedadSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ['unidad', 'liquidacion', 'unidad__propietario']
    search_fields = ['descripcion', 'unidad__codigo']

    def get_queryset(self):
        return GastoPropiedad.objects.select_related('unidad__propietario')

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def _validar_editable(self, gasto):
        if gasto.liquidacion_id:
            raise serializers.ValidationError({'detail': 'Este gasto ya se incluyó en una liquidación.'})

    def perform_update(self, serializer):
        self._validar_editable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._validar_editable(instance)
        instance.delete()


class LiquidacionViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.LiquidacionSerializer
    filterset_fields = ['estado', 'propietario', 'periodo']
    search_fields = ['propietario__nombre', 'referencia_pago']
    acciones_admin = ('anular', 'pagar', 'generar')

    def get_queryset(self):
        return Liquidacion.objects.select_related('propietario').prefetch_related('lineas__unidad')

    def _propietario(self, request):
        dato = request.data.get('propietario') or request.query_params.get('propietario')
        propietario = Cliente.objects.filter(pk=dato).first() if str(dato or '').isdigit() else None
        if propietario is None:
            raise serializers.ValidationError({'propietario': 'Selecciona un propietario.'})
        return propietario

    @action(detail=False, methods=['get'])
    def previsualizar(self, request):
        return Response(liquidaciones.previsualizar_liquidacion(self._propietario(request)))

    @action(detail=False, methods=['post'])
    def generar(self, request):
        datos = sz.GenerarLiquidacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        liquidacion = liquidaciones.generar_liquidacion(
            self._propietario(request), usuario=request.user, periodo=datos.validated_data.get('periodo'),
            observaciones=datos.validated_data['observaciones'],
        )
        return Response(self.get_serializer(liquidacion).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        datos = sz.PagarLiquidacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        liquidacion = liquidaciones.pagar_liquidacion(self.get_object(), fecha=datos.validated_data.get('fecha'), referencia=datos.validated_data['referencia'])
        return Response(self.get_serializer(liquidacion).data)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        return Response(self.get_serializer(liquidaciones.anular_liquidacion(self.get_object())).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        liquidacion = self.get_object()
        return _pdf(pdf.pdf_liquidacion(liquidacion), f'liquidacion_{liquidacion.pk}', request)


class ConsultaPropiedadViewSet(VistaConErrores, PermisosPorAccion, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = sz.ConsultaPropiedadSerializer
    http_method_names = ['get', 'patch', 'head', 'options']
    filterset_fields = ['estado', 'unidad']
    search_fields = ['nombre', 'telefono', 'email', 'mensaje']

    def get_queryset(self):
        return ConsultaPropiedad.objects.select_related('unidad')


# --- Reportes -----------------------------------------------------------------

class _ReporteView(VistaConErrores, APIView):
    permission_classes = [EsPersonal]

    def _fecha(self, request):
        valor = request.query_params.get('fecha_corte')
        return serializers.DateField().to_internal_value(valor) if valor else None


class ReporteMorosidadView(_ReporteView):
    def get(self, request):
        edificio = request.query_params.get('edificio')
        return Response(reportes.reporte_morosidad(fecha_corte=self._fecha(request), edificio_id=int(edificio) if edificio and edificio.isdigit() else None))


class RecordatoriosMorosidadView(_ReporteView):
    def get(self, request):
        edificio = request.query_params.get('edificio')
        return Response(reportes.recordatorios_morosidad(fecha_corte=self._fecha(request), edificio_id=int(edificio) if edificio and edificio.isdigit() else None))


class TableroView(_ReporteView):
    def get(self, request):
        return Response(reportes.metricas_tablero())
