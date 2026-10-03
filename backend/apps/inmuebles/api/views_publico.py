"""
API pública (sin sesión):

- Catálogo de propiedades de una inmobiliaria (`publico/propiedades/...`).
- Portal del condómino/inquilino/propietario (`portal/<token>/...`): estado de
  cuenta, datos para pagar y aviso de pago con comprobante.
"""
import logging
from datetime import timedelta

from django.db.models import Max, Min, Q
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.response import StandardResultsSetPagination
from apps.core.uploads import validar_archivo_subido
from apps.inmuebles.api.serializers import UnidadFotoSerializer, _url
from apps.inmuebles.api.views import VistaConErrores, _pdf
from apps.inmuebles.models import Cargo, ConsultaPropiedad, Recibo, Unidad
from apps.inmuebles.services import pdf, portal
from apps.inmuebles.services.cobranza import CobranzaError

logger = logging.getLogger(__name__)


class _Publica(VistaConErrores, APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'


# --- Catálogo de propiedades --------------------------------------------------

class PropiedadPublicaSerializer(serializers.ModelSerializer):
    """Lo que ve el público: sin dueño, sin dirección exacta, sin datos internos."""
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    titulo_visible = serializers.SerializerMethodField()
    portada_url = serializers.SerializerMethodField()
    fotos = serializers.SerializerMethodField()
    edificio_nombre = serializers.CharField(source='edificio.nombre', read_only=True, default=None)

    class Meta:
        model = Unidad
        fields = (
            'id', 'titulo_visible', 'tipo', 'tipo_display', 'operacion', 'descripcion', 'zona', 'ciudad', 'edificio_nombre',
            'precio_venta_usd', 'canon_usd', 'habitaciones', 'banos', 'estacionamientos', 'area_m2', 'area_construida_m2',
            'amenidades', 'portada_url', 'fotos',
        )

    def get_titulo_visible(self, obj):
        if obj.titulo:
            return obj.titulo
        lugar = obj.zona or obj.ciudad
        return f'{obj.get_tipo_display()} en {lugar}' if lugar else obj.get_tipo_display()

    def get_portada_url(self, obj):
        fotos = list(obj.fotos.all())
        return _url(fotos[0].imagen, self.context.get('request')) if fotos else None

    def get_fotos(self, obj):
        return UnidadFotoSerializer(obj.fotos.all(), many=True, context=self.context).data


class PaginacionPropiedades(StandardResultsSetPagination):
    """Siempre paginado (12 por página, máx. 48), con el mismo formato `meta.pagination` del resto de la API."""
    page_size = 12
    max_page_size = 48

    def paginate_queryset(self, queryset, request, view=None):
        self._lista_completa = False
        return PageNumberPagination.paginate_queryset(self, queryset, request, view)


def _publicas():
    return Unidad.objects.filter(activo=True, publicada=True).exclude(operacion='ninguna').select_related('edificio').prefetch_related('fotos')


class PropiedadesPublicasView(_Publica):
    def get(self, request):
        p = request.query_params
        qs = _publicas()
        operacion = p.get('operacion')
        if operacion in ('alquiler', 'venta'):
            qs = qs.filter(Q(operacion=operacion) | Q(operacion='alquiler_venta'))
        if p.get('tipo'):
            qs = qs.filter(tipo=p['tipo'])
        if p.get('zona'):
            qs = qs.filter(zona__iexact=p['zona'])
        if p.get('ciudad'):
            qs = qs.filter(ciudad__iexact=p['ciudad'])
        if p.get('habitaciones', '').isdigit():
            qs = qs.filter(habitaciones__gte=int(p['habitaciones']))
        if p.get('banos', '').isdigit():
            qs = qs.filter(banos__gte=int(p['banos']))
        campo_precio = 'canon_usd' if operacion == 'alquiler' else 'precio_venta_usd'
        for clave, filtro in (('precio_min', 'gte'), ('precio_max', 'lte')):
            try:
                if p.get(clave):
                    qs = qs.filter(**{f'{campo_precio}__{filtro}': float(p[clave])})
            except ValueError:
                raise serializers.ValidationError({clave: 'Debe ser un número.'})
        if p.get('q'):
            termino = p['q'].strip()[:80]
            qs = qs.filter(Q(titulo__icontains=termino) | Q(descripcion__icontains=termino) | Q(zona__icontains=termino) | Q(ciudad__icontains=termino))
        orden = {'precio_asc': campo_precio, 'precio_desc': f'-{campo_precio}'}.get(p.get('orden'), '-fecha_creacion')
        qs = qs.order_by(orden, '-id')

        paginador = PaginacionPropiedades()
        pagina = paginador.paginate_queryset(qs, request, view=self)
        datos = PropiedadPublicaSerializer(pagina, many=True, context={'request': request}).data
        return paginador.get_paginated_response(datos)


class PropiedadPublicaDetalleView(_Publica):
    def get(self, request, pk):
        unidad = _publicas().filter(pk=pk).first()
        if unidad is None:
            raise NotFound('Esta propiedad ya no está disponible.')
        return Response(PropiedadPublicaSerializer(unidad, context={'request': request}).data)


class FiltrosPropiedadesView(_Publica):
    """Valores disponibles para los filtros (zonas, ciudades, tipos y rangos de precio)."""

    def get(self, request):
        qs = _publicas()
        tipos = dict(Unidad.TIPO_CHOICES)
        return Response({
            'zonas': sorted({z for z in qs.values_list('zona', flat=True) if z}),
            'ciudades': sorted({c for c in qs.values_list('ciudad', flat=True) if c}),
            'tipos': [{'valor': t, 'etiqueta': tipos[t]} for t in sorted(set(qs.values_list('tipo', flat=True)))],
            'hay_alquiler': qs.filter(operacion__in=('alquiler', 'alquiler_venta')).exists(),
            'hay_venta': qs.filter(operacion__in=('venta', 'alquiler_venta')).exists(),
            'canon': qs.aggregate(min=Min('canon_usd'), max=Max('canon_usd')),
            'precio_venta': qs.aggregate(min=Min('precio_venta_usd'), max=Max('precio_venta_usd')),
        })


class ConsultaPublicaSerializer(serializers.Serializer):
    unidad = serializers.IntegerField(required=False, allow_null=True)
    nombre = serializers.CharField(min_length=2, max_length=150)
    telefono = serializers.CharField(min_length=7, max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    mensaje = serializers.CharField(required=False, allow_blank=True, max_length=1000, default='')
    # Señuelo anti-bots: un humano nunca ve ni llena este campo.
    sitio_web = serializers.CharField(required=False, allow_blank=True, default='')


class ConsultaPublicaView(_Publica):
    throttle_scope = 'inmuebles_consulta'

    def post(self, request):
        datos = ConsultaPublicaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        v = datos.validated_data
        respuesta = Response({'mensaje': 'Recibimos tu consulta. Te contactaremos pronto.'}, status=status.HTTP_201_CREATED)
        if v['sitio_web']:
            return respuesta  # bot: se responde "ok" sin guardar nada
        unidad = _publicas().filter(pk=v['unidad']).first() if v.get('unidad') else None
        if v.get('unidad') and unidad is None:
            raise NotFound('Esta propiedad ya no está disponible.')
        reciente = timezone.now() - timedelta(minutes=10)
        if ConsultaPropiedad.objects.filter(unidad=unidad, telefono=v['telefono'], fecha_creacion__gte=reciente).exists():
            return respuesta  # doble clic: no duplica
        consulta = ConsultaPropiedad.objects.create(unidad=unidad, nombre=v['nombre'], telefono=v['telefono'], email=v['email'], mensaje=v['mensaje'])
        try:
            from apps.restaurantes.push_notifications import enviar_push_a_staff
            enviar_push_a_staff('Nueva consulta de propiedad', f'{consulta.nombre} preguntó por {unidad or "una propiedad"}.', url='/admin/inmuebles/consultas')
        except Exception:
            logger.warning('No se pudo notificar la consulta %s', consulta.pk, exc_info=True)
        return respuesta


# --- Portal del condómino -----------------------------------------------------

class _Portal(_Publica):
    throttle_scope = 'inmuebles_portal'

    def acceso(self, token):
        acceso = portal.acceso_por_token(token)
        if acceso is None:
            raise NotFound('Este enlace no es válido o fue desactivado. Pídele uno nuevo a la administración.')
        return acceso


class PortalDatosView(_Portal):
    def get(self, request, token):
        return Response(portal.datos_portal(self.acceso(token)))


class PortalReportarPagoView(_Portal):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, token):
        acceso = self.acceso(token)
        comprobante = request.FILES.get('comprobante')
        if comprobante:
            comprobante = validar_archivo_subido(comprobante, permitir_pdf=True, max_mb=5, campo='comprobante')
        d = request.data
        try:
            cargos_ids = [int(x) for x in d.getlist('cargos')] if hasattr(d, 'getlist') else []
            pago = portal.reportar_pago(
                acceso, unidad_id=int(d.get('unidad') or 0), fecha_pago=serializers.DateField().to_internal_value(d.get('fecha_pago')),
                monto_pago=serializers.DecimalField(max_digits=16, decimal_places=2).to_internal_value(d.get('monto_pago')),
                moneda_pago=d.get('moneda_pago', ''), metodo=d.get('metodo', 'transferencia'), referencia=d.get('referencia', ''),
                banco=d.get('banco', ''), medio_pago_id=int(d['medio_pago']) if d.get('medio_pago') else None, cargos_ids=cargos_ids,
                comprobante=comprobante, nota=d.get('nota', ''),
            )
        except (TypeError, ValueError):
            raise serializers.ValidationError({'detail': 'Revisa los datos del pago.'})
        return Response(
            {'id': pago.pk, 'estado': pago.estado, 'mensaje': 'Recibimos tu aviso de pago. La administración lo revisará y te confirmará.'},
            status=status.HTTP_201_CREATED,
        )


class PortalReciboPdfView(_Portal):
    def get(self, request, token, recibo_id):
        acceso = self.acceso(token)
        unidades = portal.unidades_de(acceso.cliente).values_list('pk', flat=True)
        recibo = Recibo.objects.filter(pk=recibo_id, unidad_id__in=list(unidades), estado='confirmado').first()
        if recibo is None:
            raise NotFound('Recibo no encontrado.')
        return _pdf(pdf.pdf_recibo(recibo), recibo.numero, request)


class PortalEstadoCuentaPdfView(_Portal):
    def get(self, request, token, unidad_id):
        acceso = self.acceso(token)
        unidad = portal.unidades_de(acceso.cliente).filter(pk=unidad_id).first()
        if unidad is None:
            raise NotFound('Unidad no encontrada.')
        return _pdf(pdf.pdf_estado_cuenta(unidad), f'estado_cuenta_{unidad.codigo}', request)


class PortalReciboCondominioPdfView(_Portal):
    def get(self, request, token, cargo_id):
        acceso = self.acceso(token)
        unidades = list(portal.unidades_de(acceso.cliente).values_list('pk', flat=True))
        cargo = Cargo.objects.filter(pk=cargo_id, unidad_id__in=unidades, periodo_condominio__isnull=False).exclude(estado='anulado').first()
        if cargo is None:
            raise NotFound('Recibo no encontrado.')
        try:
            contenido = pdf.pdf_recibo_condominio(cargo)
        except CobranzaError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        return _pdf(contenido, f'recibo_condominio_{cargo.unidad.codigo}_{cargo.periodo}', request)
