from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrVendedor
from apps.core.throttling import ResilientScopedRateThrottle as ScopedRateThrottle
from apps.inventario.models import Producto

from ..models import Mesa, PedidoMesa, PedidoMesaItem
from ..services import cerrar_pedido_mesa, CerrarPedidoMesaError
from .serializers import (
    MesaSerializer,
    PedidoMesaSerializer,
    AgregarItemSerializer,
    CerrarPedidoSerializer,
    PedidoMesaPublicoSerializer,
    ActualizarDivisionSerializer,
)


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

        PedidoMesaItem.objects.create(
            pedido=pedido,
            producto=producto,
            cantidad=datos['cantidad'],
            precio_unitario=producto.precio or 0,
            notas=datos.get('notas') or None,
        )
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
        item.delete()
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
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='marcar-atendido')
    def marcar_atendido(self, request, pk=None):
        """Apaga las banderas de "llamar mesero"/"pedir cuenta" -- el mesero ya vio el aviso."""
        pedido = self.get_object()
        pedido.mesero_solicitado = False
        pedido.cuenta_solicitada = False
        pedido.save(update_fields=['mesero_solicitado', 'cuenta_solicitada'])
        return Response(self.get_serializer(pedido).data)

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        pedido = self.get_object()
        serializer = CerrarPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
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
        return Response(PedidoMesaPublicoSerializer(pedido).data)

    def patch(self, request, token):
        pedido = self._get_pedido(token)
        if pedido is None:
            return Response({"error": "Cuenta no encontrada o ya cerrada."}, status=status.HTTP_404_NOT_FOUND)
        if pedido.estado != 'abierto':
            return Response({"error": "Esta cuenta ya fue cerrada."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ActualizarDivisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for campo, valor in serializer.validated_data.items():
            setattr(pedido, campo, valor)
        pedido.save(update_fields=list(serializer.validated_data.keys()))
        return Response(PedidoMesaPublicoSerializer(pedido).data)


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
        return Response({"mensaje": "Se pidió la cuenta."})
