from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import models
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
import stripe as stripe_sdk
from apps.core.permissions import IsTenantAdmin
from apps.tenants.models import Plan, Subscription, Client, Domain, PlatformPaymentConfig, SubscriptionPayment
from apps.tenants.services.subscription_service import SubscriptionService
from apps.tenants.services.tenant_service import TenantService, TenantCreationError
from apps.tenants.services import subscription_payment_service as pago_suscripcion_service
from apps.tenants.services import platform_settings_service
from .serializers import (
    PlanSerializer, SubscriptionCreateSerializer, SubscriptionResponseSerializer,
    PlatformClientSerializer, TenantRegistrationSerializer, TenantProfileSerializer,
    TenantOnboardingUpdateSerializer,
    MiClienteSerializer, PlatformPaymentInfoSerializer, PlatformPaymentConfigSerializer,
    CrearPagoSuscripcionSerializer, CrearPagoSuscripcionTenantSerializer, SubscriptionPaymentSerializer,
    PlatformSettingsSerializer, RegistrationQuotaSerializer, PeriodoSuscripcionSerializer,
    ReferidoProgramaSerializer,
)

class PlanViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar los Planes de Suscripción.
    - `list`: Público, cualquiera puede ver los planes activos.
    - `retrieve`, `create`, `update`, `destroy`: Solo para administradores de la plataforma.
    """
    queryset = Plan.objects.all().order_by('precio')
    serializer_class = PlanSerializer

    def get_permissions(self):
        """
        Asigna permisos basados en la acción.
        """
        if self.action == 'list':
            # Cualquiera puede listar los planes
            self.permission_classes = [AllowAny]
        else:
            # Solo los administradores de la plataforma pueden crear, editar o eliminar planes.
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()

    def get_queryset(self):
        """
        Para la acción 'list', solo muestra los planes activos -- y si el
        visitante ya sabe para qué tipo de negocio está mirando planes
        (`?tipo_negocio=contador`), solo los que aplican a ese tipo (más los
        que aplican a todos, `tipos_negocio` vacío).
        Para otras acciones (admin), muestra todos.
        """
        if self.action == 'list':
            qs = self.queryset.filter(activo=True)
            tipo_negocio = self.request.query_params.get('tipo_negocio')
            if tipo_negocio:
                qs = qs.filter(Plan.filtro_para_tipo(tipo_negocio))
            return qs
        return self.queryset

class PlatformClientViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para que el administrador de la plataforma vea la lista de inquilinos (Clients).
    Es de solo lectura, ya que la modificación de un inquilino (cambio de plan, etc.)
    debe ser un proceso automatizado y no manual.
    """
    queryset = Client.objects.all().select_related(
        'owner', 
        'subscription__plan'
    ).prefetch_related(
        'domains'
    ).order_by('-fecha_creacion')
    
    serializer_class = PlatformClientSerializer
    permission_classes = [IsAdminUser]

class TenantRegistrationView(APIView):
    """
    Endpoint público para el registro de un nuevo cliente (tenant).
    Crea el usuario dueño, el tenant, el dominio y la suscripción inicial.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Registrar Nuevo Cliente y Tenant",
        request=TenantRegistrationSerializer,
        responses={
            201: {"description": "Registro exitoso. Se ha creado el tenant y el usuario."},
            400: {"description": "Datos inválidos o el subdominio/email ya existe."},
        }
    )
    def post(self, request):
        if not platform_settings_service.hay_cupo_disponible():
            return Response(
                {"error": "Por ahora alcanzamos el cupo de registros gratuitos disponibles. Contáctanos para más información."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TenantRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            TenantService.create_tenant(
                username=data['username'], email=data['email'],
                password=data['password'], first_name=data['first_name'],
                last_name=data['last_name'], nombre_empresa=data['nombre_empresa'], tipo_negocio=data['tipo_negocio'],
                subdomain=data['subdomain'],
                pais_codigo=data['pais_codigo'],
                plan_id=data.get('plan_id'),
                cantidad_mesas=data.get('cantidad_mesas', 6),
                codigo_referido=data.get('codigo_referido'),
            )
        except TenantCreationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error inesperado en registro de tenant: {e}") # Log para debug
            return Response({"error": "Ocurrió un error inesperado durante el registro."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Para el mensaje de respuesta, mostramos el dominio sin el puerto para consistencia.
        base_domain_with_port = getattr(settings, 'TENANT_DOMAIN', 'localhost')
        base_domain = base_domain_with_port.split(':')[0]
        return Response({"message": f"¡Registro exitoso! Tu espacio de trabajo está listo en {data['subdomain']}.{base_domain}"}, status=status.HTTP_201_CREATED)

class SubdomainAvailabilityView(APIView):
    """
    Verifica si un subdominio está disponible para ser registrado.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verificar Disponibilidad de Subdominio",
        parameters=[
            OpenApiParameter(name='subdomain', description='El subdominio a verificar (ej: mi-tienda).', required=True, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={
            200: {"description": "Respuesta sobre la disponibilidad."},
            400: {"description": "Falta el parámetro 'subdomain'."}
        }
    )
    def get(self, request):
        subdomain = request.query_params.get('subdomain', '').lower().strip()
        if not subdomain:
            return Response({"error": "El parámetro 'subdomain' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Verificar palabras reservadas
        reserved_subdomains = ['www', 'api', 'admin', 'mail', 'app', 'public', 'static']
        if subdomain in reserved_subdomains:
            return Response({"available": False, "message": "Este subdominio está reservado."}, status=status.HTTP_200_OK)
        
        # 2. Verificar si ya existe en la base de datos
        # Nos aseguramos de que el dominio base no incluya el puerto para la comparación.
        base_domain_with_port = getattr(settings, 'TENANT_DOMAIN', 'localhost')
        base_domain = base_domain_with_port.split(':')[0]
        full_domain = f"{subdomain}.{base_domain}"
        
        if Domain.objects.filter(domain=full_domain).exists():
            return Response({"available": False, "message": "Este subdominio ya está en uso."}, status=status.HTTP_200_OK)

        return Response({"available": True}, status=status.HTTP_200_OK)


class UsernameAvailabilityView(APIView):
    """
    Verifica si un nombre de usuario está disponible para el dueño de un
    tenant nuevo. El username es único a nivel de PLATAFORMA (esquema
    público, `auth.User` en SHARED_APPS) porque es con lo que se autentica
    para pagar/gestionar su suscripción -- no tiene relación con los
    usernames de empleados DENTRO de cada tenant, que viven en tablas
    `auth_user` separadas por esquema y sí pueden repetirse entre tenants.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verificar Disponibilidad de Usuario",
        parameters=[
            OpenApiParameter(name='username', description='El nombre de usuario a verificar.', required=True, type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
        ],
        responses={200: {"description": "Respuesta sobre la disponibilidad."}},
    )
    def get(self, request):
        from django.contrib.auth.models import User

        username = request.query_params.get('username', '').strip()
        if not username:
            return Response({"error": "El parámetro 'username' es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username__iexact=username).exists():
            return Response({"available": False, "message": "Este nombre de usuario ya está en uso."}, status=status.HTTP_200_OK)

        return Response({"available": True}, status=status.HTTP_200_OK)


class SubscriptionCUD(APIView):
    """
    Activación MANUAL de una suscripción, de uso exclusivo del superadmin
    (ej. cortesías, casos especiales). El flujo real para que un tenant
    active su plan es `CrearPagoSuscripcionView` + confirmación real de pago
    (`SubscriptionPaymentViewSet.confirmar` o el webhook de Stripe) -- este
    endpoint YA NO debe llamarse directamente desde el frontend del tenant,
    porque no valida ningún pago (de ahí que ahora requiera ser admin).
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Crear o Actualizar una Suscripción",
        description="Este endpoint se llama después de que un pago es confirmado por la pasarela. Crea o renueva la suscripción de un cliente a un plan.",
        request=SubscriptionCreateSerializer,
        responses={
            201: SubscriptionResponseSerializer,
            400: {"description": "Datos de entrada inválidos"},
            404: {"description": "Cliente o Plan no encontrado"},
        }
    )
    def post(self, request):
        client_id = request.data.get('client_id')
        plan_id = request.data.get('plan_id')

        if not client_id or not plan_id:
            return Response({"error": "Faltan datos requeridos (client_id, plan_id)"}, status=status.HTTP_400_BAD_REQUEST)

        # --- MEJORA DE SEGURIDAD CRÍTICA ---
        # Verificar que el usuario que hace la petición es el dueño del tenant.
        client = get_object_or_404(Client, id=client_id)
        if client.owner != request.user:
            return Response({"error": "No tienes permiso para modificar esta suscripción."}, status=status.HTTP_403_FORBIDDEN)

        # En un escenario real, aquí validaríamos que el pago en la pasarela (ej. PagoMovil o Stripe)
        # fue exitoso antes de llamar a create_subscription.
        
        try:
            sub = SubscriptionService.create_subscription(client_id=client_id, plan_id=plan_id)
            serializer = SubscriptionResponseSerializer(sub)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Client.DoesNotExist:
            return Response({"error": "Cliente no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Plan.DoesNotExist:
            return Response({"error": "Plan no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TenantProfileView(generics.RetrieveUpdateAPIView):
    """
    Devuelve el perfil del tenant actual basado en el subdominio de la petición.
    Esencial para que el frontend conozca el contexto (ej: tipo_negocio).

    También acepta PATCH -- pero solo para marcar `onboarding_completado`
    (ver `TenantOnboardingUpdateSerializer`): el resto de campos del perfil
    no son editables desde este endpoint.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """
        Devuelve el objeto tenant asociado a la petición actual.
        """
        return self.request.tenant

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return TenantOnboardingUpdateSerializer
        return TenantProfileSerializer


class ReferidoProgramaView(APIView):
    """
    Resumen del programa de referidos para el dueño del tenant actual: su
    código de invitación (su propio `schema_name`), cuántos negocios ha
    invitado y en qué estado, y cuántos meses gratis ha ganado en total.
    Ver `apps.tenants.models.Referido` y
    `subscription_payment_service._recompensar_referido_si_aplica`.
    """
    permission_classes = [IsTenantAdmin]

    @extend_schema(summary="Obtener el resumen del programa de referidos del tenant actual", responses=ReferidoProgramaSerializer)
    def get(self, request):
        from apps.tenants.models import Referido

        tenant = request.tenant
        referidos = Referido.objects.filter(referente=tenant).select_related('referido').order_by('-fecha_registro')
        recompensados = referidos.filter(estado='recompensado')

        # Mismo patrón que `CrearPagoSuscripcionTenantView` -- el link debe
        # apuntar al dominio RAÍZ (sin subdominio de tenant), que es donde
        # vive el formulario de registro público.
        base_frontend = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000')

        data = {
            'codigo_referido': tenant.schema_name,
            # El formulario de registro público vive en `/login` (ver
            # `src/app/main/login/page.tsx`, que ya lee `?plan=`) -- no
            # existe una ruta `/registro` separada.
            'link_invitacion': f'{base_frontend}/login?ref={tenant.schema_name}',
            'total_referidos': referidos.count(),
            'referidos_pendientes': referidos.filter(estado='pendiente').count(),
            'referidos_recompensados': recompensados.count(),
            'meses_ganados': sum(r.meses_bonus for r in recompensados),
            'referidos': list(referidos),
        }
        serializer = ReferidoProgramaSerializer(data)
        return Response(serializer.data)


# --- COBRO DE SUSCRIPCIONES SAAS (el tenant le paga a LA PLATAFORMA) ---
# No confundir con `apps.pagos` (SHARED_APPS -> TENANT_APPS): esa app es la
# pasarela que cada tenant configura para cobrarle a SUS clientes finales en
# su catálogo público. Aquí el flujo de dinero es el opuesto: el dueño del
# tenant le paga a la plataforma para mantener su suscripción activa.

class MiClienteView(generics.RetrieveAPIView):
    """
    Devuelve el `Client` (tenant) del usuario autenticado en el esquema
    público. Lo usa la pantalla de pago de suscripción para saber a quién
    cobrarle y qué país eligió en el onboarding (determina el método de pago).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MiClienteSerializer

    def get_object(self):
        return get_object_or_404(
            Client.objects.select_related('subscription__plan'), owner=self.request.user
        )


class PlatformPaymentInfoView(APIView):
    """
    Datos PÚBLICOS de cobro de la plataforma (Pago Móvil/Zelle de Carlos y la
    publishable key de Stripe). Nunca expone claves secretas.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        config = pago_suscripcion_service.obtener_config_pago_plataforma()
        return Response(PlatformPaymentInfoSerializer(config).data)


class TasaBcvPlataformaView(APIView):
    """
    Tasa oficial BCV del día, para que el panel de suscripción muestre el
    equivalente en bolívares del monto en USD que cobra la plataforma (Pago
    Móvil solo admite bolívares -- antes el tenant tenía que calcularlo a
    mano). No depende de la configuración de moneda de ningún tenant: usa
    directamente el mismo servicio que `bcv_service` usa para las tasas
    operativas del tenant, pero sin escribir nada en base de datos.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.configuracion.services.bcv_service import obtener_tasa_bcv_oficial, BcvApiError
        try:
            tasa = obtener_tasa_bcv_oficial()
        except BcvApiError:
            return Response({"tasa": None})
        return Response({"tasa": str(tasa)})


class PlatformPaymentConfigView(generics.RetrieveUpdateAPIView):
    """
    CRUD (get/patch) de la configuración de cobro de la plataforma, solo
    para el superadmin: aquí Carlos carga SU PROPIO Pago Móvil/Zelle y sus
    propias credenciales de Stripe (no las de un tenant).
    """
    permission_classes = [IsAdminUser]
    serializer_class = PlatformPaymentConfigSerializer

    def get_object(self):
        return pago_suscripcion_service.obtener_config_pago_plataforma()


class CrearPagoSuscripcionView(APIView):
    """
    Punto de entrada real para que el dueño de un tenant pague su
    suscripción. El método de pago queda determinado por `Client.pais_codigo`
    (Venezuela -> Pago Móvil/Zelle manual; resto -> Stripe), este endpoint
    solo valida que el método elegido coincida con lo esperado para ese país.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Iniciar el pago de una suscripción",
        request=CrearPagoSuscripcionSerializer,
        responses={201: {"description": "Pago pendiente creado (y, si es Stripe, URL de checkout)."}},
    )
    def post(self, request):
        serializer = CrearPagoSuscripcionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = get_object_or_404(Client, id=data['client_id'])
        if client.owner != request.user:
            return Response({"error": "No tienes permiso para pagar la suscripción de este cliente."}, status=status.HTTP_403_FORBIDDEN)
        plan = get_object_or_404(Plan, id=data['plan_id'], activo=True)

        base_frontend = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000')
        try:
            pago, checkout_url = pago_suscripcion_service.crear_pago_suscripcion(
                client=client,
                plan=plan,
                metodo=data['metodo'],
                referencia=data.get('referencia', ''),
                periodo=data.get('periodo', 'mensual'),
                success_url=f"{base_frontend}/pago?stripe=success&subdominio={client.schema_name}",
                cancel_url=f"{base_frontend}/pago?stripe=cancel&plan={plan.slug or ''}&subdominio={client.schema_name}",
            )
        except pago_suscripcion_service.PagoSuscripcionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "pago_id": pago.id,
            "estado": pago.estado,
            "metodo": pago.metodo,
            "periodo": pago.periodo,
            "monto": str(pago.monto),
            "checkout_url": checkout_url,
        }, status=status.HTTP_201_CREATED)


class CrearPagoSuscripcionDesdeAdminView(APIView):
    """
    Mismo flujo que `CrearPagoSuscripcionView`, pero pensado para llamarse
    DESDE el propio panel del tenant (`/admin/suscripcion`), autenticado como
    empleado/administrador del tenant -- no como el dueño en el esquema
    público.

    Estos son dos sistemas de login separados a propósito (el dueño paga la
    plataforma; el empleado opera el negocio), con tokens que NO son
    intercambiables entre sí (cada uno se valida contra la tabla `auth_user`
    de un esquema distinto). Antes, la única forma de gestionar el plan era
    cruzar al dominio raíz `/pago` y volver a iniciar sesión como el dueño
    -- aquí no hace falta: como la petición ya llegó enrutada al esquema del
    tenant, `request.tenant` YA ES el `Client` a cobrar, sin tener que
    resolverlo por `owner == request.user`.
    """
    permission_classes = [IsTenantAdmin]

    @extend_schema(
        summary="Iniciar el pago de una suscripción (desde el panel del tenant)",
        request=CrearPagoSuscripcionTenantSerializer,
        responses={201: {"description": "Pago pendiente creado (y, si es Stripe, URL de checkout)."}},
    )
    def post(self, request):
        serializer = CrearPagoSuscripcionTenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = request.tenant
        plan = get_object_or_404(Plan, id=data['plan_id'], activo=True)

        # A diferencia del flujo del dueño, aquí el redirect de Stripe debe
        # volver al SUBDOMINIO del tenant (no al dominio raíz) -- si no, el
        # navegador vuelve a `/admin/suscripcion` sin el contexto del tenant.
        base_frontend = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:3000')
        base_sin_protocolo = base_frontend.split('://', 1)[-1]
        tenant_frontend = f"http://{client.schema_name}.{base_sin_protocolo}"
        try:
            pago, checkout_url = pago_suscripcion_service.crear_pago_suscripcion(
                client=client,
                plan=plan,
                metodo=data['metodo'],
                referencia=data.get('referencia', ''),
                periodo=data.get('periodo', 'mensual'),
                success_url=f"{tenant_frontend}/admin/suscripcion?stripe=success",
                cancel_url=f"{tenant_frontend}/admin/suscripcion?stripe=cancel",
            )
        except pago_suscripcion_service.PagoSuscripcionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "pago_id": pago.id,
            "estado": pago.estado,
            "metodo": pago.metodo,
            "periodo": pago.periodo,
            "monto": str(pago.monto),
            "checkout_url": checkout_url,
        }, status=status.HTTP_201_CREATED)


class PeriodosSuscripcionView(APIView):
    """
    Públicos: los períodos de facturación disponibles (mensual/trimestral/
    anual) con sus descuentos, para que el frontend calcule y muestre los
    mismos montos que realmente cobrará `crear_pago_suscripcion`.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        data = [
            {"codigo": codigo, **info}
            for codigo, info in pago_suscripcion_service.PERIODOS_SUSCRIPCION.items()
        ]
        return Response(PeriodoSuscripcionSerializer(data, many=True).data)


@method_decorator(csrf_exempt, name='dispatch')
class StripeSuscripcionWebhookView(APIView):
    """
    Webhook de Stripe para confirmar automáticamente el pago de una
    suscripción (cuenta de Stripe de LA PLATAFORMA, distinta de la de cada
    tenant en `apps.pagos.StripeConfig`).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        try:
            pago_suscripcion_service.procesar_webhook_stripe(payload, sig_header)
        except pago_suscripcion_service.StripePlataformaNoConfiguradoError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except (stripe_sdk.error.SignatureVerificationError, ValueError):
            return Response({"error": "Firma de webhook inválida."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"received": True}, status=status.HTTP_200_OK)


class SubscriptionPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vista de superadmin para revisar y confirmar/rechazar pagos de
    suscripción manuales (Pago Móvil/Zelle) -- los de Stripe normalmente se
    confirman solos vía webhook, pero también quedan visibles aquí.
    """
    queryset = SubscriptionPayment.objects.select_related('client', 'plan', 'confirmado_por').all()
    serializer_class = SubscriptionPaymentSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['estado', 'metodo']

    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        try:
            pago = pago_suscripcion_service.confirmar_pago(pk, admin_user=request.user)
        except pago_suscripcion_service.PagoSuscripcionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except SubscriptionPayment.DoesNotExist:
            return Response({"error": "Pago no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SubscriptionPaymentSerializer(pago).data)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = request.data.get('motivo', '')
        try:
            pago = pago_suscripcion_service.rechazar_pago(pk, admin_user=request.user, motivo=motivo)
        except pago_suscripcion_service.PagoSuscripcionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except SubscriptionPayment.DoesNotExist:
            return Response({"error": "Pago no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SubscriptionPaymentSerializer(pago).data)


class RegistrationQuotaView(APIView):
    """Cuántos cupos de registro gratuito quedan (público, para mostrarlo en el formulario de alta)."""
    permission_classes = [AllowAny]

    def get(self, request):
        config = platform_settings_service.obtener_configuracion()
        data = {
            'cupos_restantes': platform_settings_service.cupos_restantes(),
            'cupo_total': config.limite_registros_gratis,
        }
        return Response(RegistrationQuotaSerializer(data).data)


class PlatformSettingsView(generics.RetrieveUpdateAPIView):
    """Configuración global de la plataforma (cupo gratis, días de gracia), solo superadmin."""
    permission_classes = [IsAdminUser]
    serializer_class = PlatformSettingsSerializer

    def get_object(self):
        return platform_settings_service.obtener_configuracion()
