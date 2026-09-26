import random

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle
from apps.inventario.models import Producto

from ..models import Mesa, PedidoMesa, PedidoMesaItem, PushSubscription
from ..services import cerrar_pedido_mesa, CerrarPedidoMesaError
from ..realtime import notificar_pedido_actualizado, notificar_mesas_actualizadas
from ..push_notifications import enviar_push_a_staff
from .serializers import (
    MesaSerializer,
    PedidoMesaSerializer,
    AgregarItemSerializer,
    CerrarPedidoSerializer,
    PedidoMesaPublicoSerializer,
    ActualizarDivisionSerializer,
    AsignarPersonaItemSerializer,
    PushSubscriptionSerializer,
)


def _refrescar_cache_items(pedido: PedidoMesa) -> None:
    """
    `self.get_object()` trae `pedido` con `items` ya prefetched (foto de
    ANTES de esta mutación) -- sin invalidar ese cache, la serialización de
    la respuesta HTTP y el push por WebSocket (`notificar_pedido_actualizado`,
    que serializa este mismo objeto) seguían devolviendo la lista vieja de
    ítems justo después de crear/editar/borrar uno, y el cliente optimista
    del frontend recibía esa respuesta "confirmando" el estado viejo -- el
    ítem parpadeaba (aparecía y desaparecía) hasta el siguiente poll/push que
    sí leía de la base de datos.
    """
    if hasattr(pedido, '_prefetched_objects_cache'):
        pedido._prefetched_objects_cache.pop('items', None)


class MesaViewSet(viewsets.ModelViewSet):
    queryset = Mesa.objects.filter(activo=True).order_by('numero')
    serializer_class = MesaSerializer
    permission_classes = [IsAdminOrVendedor]

    def perform_destroy(self, instance):
        # Baja lógica -- una mesa con pedidos históricos no debe desaparecer
        # de verdad (rompería el historial de esos pedidos).
        instance.activo = False
        instance.save(update_fields=['activo'])


class PedidoMesaViewSet(viewsets.ModelViewSet):
    """
    Pedidos de mesa del panel (requiere sesión). Crear uno nuevo = "abrir"
    la mesa; las acciones `agregar_item`/`quitar_item`/`cerrar` son el resto
    del ciclo de vida -- no se edita un pedido con un PATCH genérico porque
    cada paso tiene sus propias reglas (ver cada acción).
    """

    queryset = PedidoMesa.objects.select_related('mesa', 'mesero', 'cliente').prefetch_related('items__producto')
    serializer_class = PedidoMesaSerializer
    permission_classes = [IsAdminOrVendedor]
    http_method_names = ['get', 'post', 'head', 'options']
    # Sin paginar -- la vista de cocina pide TODOS los pedidos abiertos
    # (`?estado=abierto`) de una vez; con el default de 20 por página, un
    # restaurante con más de 20 mesas abiertas a la vez perdería pedidos
    # completos de la vista sin ningún aviso.
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def create(self, request, *args, **kwargs):
        mesa_id = request.data.get('mesa')
        if not mesa_id:
            return Response({"error": "El campo 'mesa' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        mesa = Mesa.objects.filter(pk=mesa_id, activo=True).first()
        if mesa is None:
            return Response({"error": "Mesa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if mesa.pedido_abierto is not None:
            return Response({"error": "Esta mesa ya tiene un pedido abierto."}, status=status.HTTP_400_BAD_REQUEST)

        pedido = PedidoMesa.objects.create(mesa=mesa, mesero=request.user, cliente_id=request.data.get('cliente'))
        notificar_mesas_actualizadas()
        return Response(self.get_serializer(pedido).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def agregar_item(self, request, pk=None):
        pedido = self.get_object()
        if pedido.estado != 'abierto':
            return Response({"error": "Este pedido ya está cerrado."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AgregarItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        producto = Producto.objects.filter(pk=datos['producto_id'], activo=True).first()
        if producto is None:
            return Response({"error": "Producto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        notas = datos.get('notas') or None
        # Si ya hay una línea del mismo producto sin asignar a una persona y
        # sin marcar como preparada, se suma la cantidad ahí (1x -> 2x) en
        # vez de crear otra línea separada del mismo producto -- así se
        # comporta como el POS. No se suma a una línea ya asignada/preparada
        # porque eso corrompería la asignación de esa persona o le pediría a
        # cocina algo que ya entregó.
        item_existente = pedido.items.filter(
            producto=producto, notas=notas, persona_asignada__isnull=True, preparado=False,
        ).first()
        if item_existente:
            item_existente.cantidad += datos['cantidad']
            item_existente.save(update_fields=['cantidad'])
        else:
            PedidoMesaItem.objects.create(
                pedido=pedido,
                producto=producto,
                cantidad=datos['cantidad'],
                precio_unitario=producto.precio or 0,
                notas=notas,
                departamento=producto.departamento,
            )
        _refrescar_cache_items(pedido)
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'], url_path='quitar-item')
    def quitar_item(self, request, pk=None):
        pedido = self.get_object()
        if pedido.estado != 'abierto':
            return Response({"error": "Este pedido ya está cerrado."}, status=status.HTTP_400_BAD_REQUEST)

        item_id = request.data.get('item_id')
        item = pedido.items.filter(pk=item_id).first()
        if item is None:
            return Response({"error": "Ítem no encontrado en este pedido."}, status=status.HTTP_404_NOT_FOUND)
        # Simétrico a agregar_item: por defecto quita de a uno en vez de
        # borrar toda la línea de una vez (para no perder el resto de la
        # cantidad con un solo tap del "-"); `eliminar_todo` es lo que usa el
        # botón de basura para quitar la línea completa de un solo golpe.
        if request.data.get('eliminar_todo') or item.cantidad <= 1:
            item.delete()
        else:
            item.cantidad -= 1
            item.save(update_fields=['cantidad'])
        _refrescar_cache_items(pedido)
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """
        Libera una mesa abierta por error (el mesero tocó la mesa pero no
        llegó a pedir nada) -- solo se permite si el pedido sigue vacío, para
        no borrar por accidente un pedido con ítems reales ya cargados.
        """
        pedido = self.get_object()
        if pedido.estado != 'abierto':
            return Response({"error": "Este pedido ya está cerrado."}, status=status.HTTP_400_BAD_REQUEST)
        if pedido.items.exists():
            return Response({"error": "Este pedido ya tiene ítems -- no se puede cancelar así."}, status=status.HTTP_400_BAD_REQUEST)
        pedido.delete()
        notificar_mesas_actualizadas()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='marcar-item-preparado')
    def marcar_item_preparado(self, request, pk=None):
        """Para la vista de cocina -- alterna si un plato/bebida ya se preparó."""
        pedido = self.get_object()
        item_id = request.data.get('item_id')
        item = pedido.items.filter(pk=item_id).first()
        if item is None:
            return Response({"error": "Ítem no encontrado en este pedido."}, status=status.HTTP_404_NOT_FOUND)
        item.preparado = not item.preparado
        if item.preparado:
            item.preparado_por = request.user
            item.fecha_preparado = timezone.now()
        else:
            item.preparado_por = None
            item.fecha_preparado = None
        item.save(update_fields=['preparado', 'preparado_por', 'fecha_preparado'])
        _refrescar_cache_items(pedido)
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'], url_path='asignar-persona-item')
    def asignar_persona_item(self, request, pk=None):
        """Staff puede asignar/reasignar un ítem a una persona -- lo mismo que el comensal puede hacer desde el QR."""
        pedido = self.get_object()
        serializer = AsignarPersonaItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = pedido.items.filter(pk=serializer.validated_data['item_id']).first()
        if item is None:
            return Response({"error": "Ítem no encontrado en este pedido."}, status=status.HTTP_404_NOT_FOUND)
        item.persona_asignada = serializer.validated_data['persona_asignada']
        item.save(update_fields=['persona_asignada'])
        _refrescar_cache_items(pedido)
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'], url_path='comprobante-pago', parser_classes=[MultiPartParser, FormParser])
    def subir_comprobante_pago(self, request, pk=None):
        pedido = self.get_object()
        archivo = request.FILES.get('comprobante_pago')
        if not archivo:
            return Response({"error": "No se recibió ningún archivo."}, status=status.HTTP_400_BAD_REQUEST)
        pedido.comprobante_pago = archivo
        pedido.save(update_fields=['comprobante_pago'])
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='marcar-atendido')
    def marcar_atendido(self, request, pk=None):
        """Apaga las banderas de "llamar mesero"/"pedir cuenta" -- el mesero ya vio el aviso."""
        pedido = self.get_object()
        pedido.mesero_solicitado = False
        pedido.cuenta_solicitada = False
        pedido.save(update_fields=['mesero_solicitado', 'cuenta_solicitada'])
        notificar_pedido_actualizado(pedido)
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        pedido = self.get_object()
        serializer = CerrarPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'cliente_id' in serializer.validated_data:
            pedido.cliente_id = serializer.validated_data['cliente_id']
            pedido.save(update_fields=['cliente'])
        try:
            factura = cerrar_pedido_mesa(
                pedido=pedido,
                metodo_pago_id=serializer.validated_data['metodo_pago_id'],
                usuario=request.user,
                condicion_pago=serializer.validated_data['condicion_pago'],
                moneda_id=serializer.validated_data.get('moneda_id'),
            )
        except CerrarPedidoMesaError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        notificar_pedido_actualizado(pedido)
        return Response({"mensaje": "Pedido cobrado.", "factura_id": factura.id, "correlativo": factura.correlativo})


class PedidoMesaPublicoView(APIView):
    """
    Lo que abre un comensal al escanear el QR de su mesa -- sin login, solo
    con el token opaco del pedido (ver `PedidoMesa.token_publico`). Se
    "vuelve a mostrar" la misma información a todo el que escanee: es una
    cuenta compartida entre el grupo, no una vista privada por persona.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def _get_pedido(self, token):
        return PedidoMesa.objects.select_related('mesa').prefetch_related('items__producto').filter(
            token_publico=token,
        ).first()

    def get(self, request, token):
        pedido = self._get_pedido(token)
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PedidoMesaPublicoSerializer(pedido, context={'request': request}).data)

    def patch(self, request, token):
        pedido = self._get_pedido(token)
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        if pedido.estado != 'abierto':
            return Response({"error": "Esta cuenta ya fue cerrada."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ActualizarDivisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        pin_recibido = datos.pop('pin_anfitrion', None)

        campos_a_guardar = list(datos.keys())
        if 'datos_pago_anfitrion' in datos:
            # Ya hay datos guardados con un PIN -- para cambiarlos hace falta
            # ese mismo PIN (sin esto, cualquiera del grupo podía sobreescribir
            # los datos bancarios de otra persona sin darse cuenta o adrede).
            if pedido.datos_pago_anfitrion and pedido.pin_anfitrion:
                if pin_recibido != pedido.pin_anfitrion:
                    return Response(
                        {"error": "PIN incorrecto -- solo quien registró estos datos puede editarlos."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            elif datos['datos_pago_anfitrion']:
                # Primera vez que se guardan datos reales -- se fija el PIN
                # (el que mandó el cliente, o uno generado si no mandó nada).
                pedido.pin_anfitrion = pin_recibido or f'{random.randint(0, 9999):04d}'
                campos_a_guardar.append('pin_anfitrion')

        for campo, valor in datos.items():
            setattr(pedido, campo, valor)
        pedido.save(update_fields=campos_a_guardar)
        notificar_pedido_actualizado(pedido)

        respuesta = PedidoMesaPublicoSerializer(pedido, context={'request': request}).data
        # El PIN se devuelve UNA sola vez, en la misma respuesta que lo crea,
        # para que quien lo acaba de fijar lo pueda anotar -- después de esto
        # nunca más viaja en ninguna respuesta (ver `tiene_pin_anfitrion` en
        # el serializer, que solo dice si existe, no cuál es).
        if 'pin_anfitrion' in campos_a_guardar:
            respuesta['pin_anfitrion_nuevo'] = pedido.pin_anfitrion
        return Response(respuesta)


class AsignarPersonaItemPublicoView(APIView):
    """El comensal indica a cuál de las N personas corresponde cada ítem, para dividir la cuenta por consumo real."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def post(self, request, token):
        pedido = PedidoMesa.objects.filter(token_publico=token, estado='abierto').first()
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AsignarPersonaItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = pedido.items.filter(pk=serializer.validated_data['item_id']).first()
        if item is None:
            return Response({"error": "Ítem no encontrado en esta cuenta."}, status=status.HTTP_404_NOT_FOUND)

        persona = serializer.validated_data['persona_asignada']
        if persona is not None and persona > pedido.division_personas:
            return Response({"error": "Esa persona no existe en la división actual."}, status=status.HTTP_400_BAD_REQUEST)

        item.persona_asignada = persona
        item.save(update_fields=['persona_asignada'])
        notificar_pedido_actualizado(pedido)
        return Response(PedidoMesaPublicoSerializer(pedido, context={'request': request}).data)


class SubirComprobantePagoPublicoView(APIView):
    """Quien ya transfirió sube la captura del comprobante -- visible para todo el grupo y para el mesero."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, token):
        pedido = PedidoMesa.objects.filter(token_publico=token, estado='abierto').first()
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        archivo = request.FILES.get('comprobante_pago')
        if not archivo:
            return Response({"error": "No se recibió ningún archivo."}, status=status.HTTP_400_BAD_REQUEST)
        pedido.comprobante_pago = archivo
        pedido.save(update_fields=['comprobante_pago'])
        notificar_pedido_actualizado(pedido)
        return Response(PedidoMesaPublicoSerializer(pedido, context={'request': request}).data)


class LlamarMeseroPublicoView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def post(self, request, token):
        pedido = PedidoMesa.objects.filter(token_publico=token, estado='abierto').first()
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        pedido.mesero_solicitado = True
        pedido.save(update_fields=['mesero_solicitado'])
        notificar_pedido_actualizado(pedido)
        enviar_push_a_staff(f'Mesa {pedido.mesa.numero} llama al mesero', 'Toca para ver el pedido.')
        return Response({"mensaje": "Se avisó al mesero."})


class PedirCuentaPublicoView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'catalogo'

    def post(self, request, token):
        pedido = PedidoMesa.objects.filter(token_publico=token, estado='abierto').first()
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        pedido.cuenta_solicitada = True
        pedido.save(update_fields=['cuenta_solicitada'])
        notificar_pedido_actualizado(pedido)
        enviar_push_a_staff(f'Mesa {pedido.mesa.numero} pide la cuenta', 'Toca para cobrar.')
        return Response({"mensaje": "Se pidió la cuenta."})


class PushSubscriptionView(APIView):
    """Alta/baja de una suscripción de Web Push del staff logueado (ver `apps.restaurantes.push_notifications`)."""

    permission_classes = [IsAdminOrVendedor]

    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushSubscription.objects.update_or_create(
            endpoint=serializer.validated_data['endpoint'],
            defaults={
                'usuario': request.user,
                'p256dh': serializer.validated_data['p256dh'],
                'auth': serializer.validated_data['auth'],
            },
        )
        return Response({"mensaje": "Suscripción registrada."}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        endpoint = request.data.get('endpoint')
        if endpoint:
            PushSubscription.objects.filter(endpoint=endpoint).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
