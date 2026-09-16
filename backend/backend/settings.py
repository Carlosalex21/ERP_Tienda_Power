import sys
from pathlib import Path
import os
from datetime import timedelta
import dj_database_url

# Import dotenv
from dotenv import load_dotenv # type: ignore
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / '.env', override=True)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-dev-key-123456")

# En producción (Coolify), DEBUG será 'False'.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# --- Configuración de ALLOWED_HOSTS para Multi-Tenancy ---
# En desarrollo (DEBUG=True) se permiten todos los hosts para no chocar con
# el middleware de tenants al probar subdominios locales. En producción es
# obligatorio declarar los hosts explícitamente vía la variable de entorno.
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*' if DEBUG else '').split(',')

# --- Email (recuperación de contraseña, notificaciones) ---
# Sin backend SMTP configurado, Django intenta conectar a localhost:25 y
# falla/cuelga. Por defecto usamos el backend de consola (imprime el correo
# en los logs del servidor, útil en dev); en producción se fija por env var.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@erpsystem.local')

# Dominio (host:puerto) donde vive el FRONTEND, usado para armar links de
# vuelta al frontend (recuperación de contraseña, etc.) -- separado de
# `TENANT_DOMAIN` (que es el dominio del propio backend).
FRONTEND_BASE_DOMAIN = os.getenv('FRONTEND_BASE_DOMAIN', 'localhost:3000')
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:3000')

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY", SECRET_KEY),
    "AUDIENCE": os.getenv("JWT_AUDIENCE", "erp-saas"),
    "ISSUER": os.getenv("JWT_ISSUER", "erp-api"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_OBTAIN_SERIALIZER": "apps.usuarios.api.serializers.MyTokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "apps.usuarios.api.serializers.MyTokenRefreshSerializer",
    "TOKEN_VERIFY_SERIALIZER": "rest_framework_simplejwt.serializers.TokenVerifySerializer",
    "TOKEN_BLACKLIST_SERIALIZER": "rest_framework_simplejwt.serializers.TokenBlacklistSerializer",
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.core.authentication.TenantBoundJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'apps.core.renderers.StandardJSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.response.StandardResultsSetPagination',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'apps.core.exception_handler.custom_exception_handler',

    'DEFAULT_THROTTLE_CLASSES': (
        'apps.core.throttling.ResilientAnonRateThrottle',
        'apps.core.throttling.ResilientUserRateThrottle',
        'apps.core.throttling.ResilientScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        # En desarrollo subimos los límites para no bloquear operaciones simultáneas
        # del panel (dashboard + POS + inventario). En producción se ajustan vía env.
        'anon': os.getenv('THROTTLE_ANON', '120/min'),
        'user': os.getenv('THROTTLE_USER', '1000/min'),
        'login': os.getenv('THROTTLE_LOGIN', '20/min'),
        'catalogo': os.getenv('THROTTLE_CATALOGO', '300/min'),
        'password_reset': os.getenv('THROTTLE_PASSWORD_RESET', '5/min'),
    },
}


# =========================================================
# CONFIGURACIÓN MULTI-TENANT (django-tenants)
# =========================================================

# Aplicaciones Compartidas (Esquema 'public')
SHARED_APPS = [
    'django_tenants', 
    'drf_spectacular',

    # Apps de Django globales
    "django.contrib.admin",
    "django.contrib.auth", # Autenticación del admin global
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Librerias globales
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",

    # App para gestionar los subdominios y suscripciones
    'apps.tenants', 

]


# Aplicaciones del Inquilino (Esquema 'cliente1', 'cliente2')
TENANT_APPS = [
    "django.contrib.auth", # Permite que cada cliente tenga sus propios usuarios
    "django.contrib.contenttypes",
    "rest_framework_simplejwt.token_blacklist",

    #APPS
    'apps.common',
    'apps.usuarios',
    'apps.auditoria',
    'apps.configuracion',
    'apps.clientes',
    'apps.proveedores',
    'apps.inventario',
    'apps.pagos', # Nueva app de pagos
    'apps.facturacion',
    'apps.catalogo_publico',
    'apps.rrhh',
    'apps.reportes',
    
    # Si 'erp' y 'tienda' aún tienen modelos viejos, déjalos aquí temporalmente
    #'erp',
    #'tienda',
]
# La forma correcta de combinar las listas, manteniendo el orden y sin duplicados.
INSTALLED_APPS = SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]

# Definición de modelos para Tenants y Dominios
TENANT_MODEL = "tenants.Client"
TENANT_DOMAIN_MODEL = "tenants.Domain"
TENANT_DOMAIN = os.getenv('TENANT_DOMAIN', 'localhost:8000')

# Enrutador de base de datos
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

# CONFIGURACIÓN DE ENRUTAMIENTO (URLs) MULTI-TENANT
ROOT_URLCONF = "backend.urls_tenants"
PUBLIC_SCHEMA_URLCONF = "backend.urls_public" 

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Para servir archivos estáticos en producción
    "corsheaders.middleware.CorsMiddleware",
    # Va DESPUÉS de CorsMiddleware a propósito: esta corta la cadena y
    # devuelve un 402 directamente (sin llamar a get_response) cuando la
    # suscripción venció. Si fuera anterior a CorsMiddleware, esa respuesta
    # nunca pasaría por él en el camino de vuelta y el navegador la
    # bloqueaba por CORS (net::ERR_FAILED) en vez de mostrar el 402.
    "apps.tenants.middleware.SubscriptionGateMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Va DESPUÉS de AuthenticationMiddleware a propósito: necesita
    # `request.user` ya resuelto para saber quién firma cada registro de
    # auditoría (ver `apps.auditoria.services.registrar`).
    "apps.auditoria.middleware.AuditoriaMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- Configuración de CORS (producción: restringido por defecto) ---
# En desarrollo se puede permitir todo con CORS_ALLOW_ALL_ORIGINS=True.
# En producción debe ser False.
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'False') == 'True'

# Esta es la forma automática y segura de permitir todos tus subdominios en producción.
TENANT_DOMAIN_CLEAN = os.getenv('TENANT_DOMAIN', 'localhost').split(':')[0] # 'localhost:8000' -> 'localhost'
CORS_ALLOWED_ORIGIN_REGEXES = [
    # Permite el frontend de desarrollo
    r"^http://localhost:3000\Z",
    r"^http://127.0.0.1:3000\Z",
    r"^http://localhost:3001\Z",
    r"^http://127.0.0.1:3001\Z",
    # Permite todos los subdominios de tu dominio de tenants
    r"^https?://\w+\.{}\Z".format(TENANT_DOMAIN_CLEAN),
    r"^https?://\w+\.{}(:\d+)?\Z".format(TENANT_DOMAIN_CLEAN),
]

# Orígenes explícitos permitidos (además de los regex).
CORS_ALLOWED_ORIGINS = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001',
).split(',')


CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant",
]
CORS_EXPOSE_HEADERS = [
    "Content-Disposition",
    "X-Total-Count",
]

CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# Cookies de autenticación JWT
JWT_ACCESS_COOKIE_NAME = os.getenv('JWT_ACCESS_COOKIE_NAME', 'access_token')
JWT_REFRESH_COOKIE_NAME = os.getenv('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
JWT_COOKIE_SECURE = os.getenv('JWT_COOKIE_SECURE', 'False') == 'True'
JWT_COOKIE_SAMESITE = os.getenv('JWT_COOKIE_SAMESITE', 'Lax')
JWT_COOKIE_HTTPONLY = os.getenv('JWT_COOKIE_HTTPONLY', 'True') == 'True'


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"


# BASE DE DATOS (Multi-Tenant)
if 'DATABASE_URL' in os.environ:
    # Producción (Coolify)
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=False)
    }
    # Usamos el motor de base de datos de django-tenants para asegurar la funcionalidad multi-tenant.
    DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'
else:
    # Desarrollo Local
    # CONN_MAX_AGE reutiliza la conexión TCP a Postgres entre requests en vez
    # de abrir una nueva por cada petición (comportamiento por defecto de
    # Django sin este valor). django-tenants resetea el search_path en cada
    # request sin importar esto, así que es seguro con multi-tenancy.
    DATABASES = {
        'default': {
            'ENGINE': 'django_tenants.postgresql_backend',
            'NAME': 'emp_system_saas', #
            'USER': 'postgres',
            'PASSWORD': os.getenv('DB_PASSWORD', "carlosalex21"), # CAMBIARLO POR PASSWORD LOCAL
            'HOST': 'localhost',
            'PORT': '5432',
            'CONN_MAX_AGE': 60,
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


# Internationalization
LANGUAGE_CODE = "es-es"
TIME_ZONE = "UTC" 
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# WooCommerce Config
WOOCOMMERCE_CONFIG = {
    "url": os.getenv("WOOCOMMERCE_URL"),
    "consumer_key": os.getenv("WOOCOMMERCE_KEY"),
    "consumer_secret": os.getenv("WOOCOMMERCE_SECRET"),
    "wp_api": True,
    "version": "wc/v3",
    "timeout": 20 
}

# =========================================================
# CACHÉ Redis
# =========================================================
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/1')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'erp_saas',
        'TIMEOUT': int(os.getenv('CACHE_TIMEOUT', '300')),
        # Sin esto, redis-py usa timeouts de conexión por defecto (varios
        # segundos, y en Windows la resolución de 'localhost' puede tardar
        # aún más). Si Redis está caído, cada get/set/throttle-check paga esa
        # espera completa ANTES de fallar -- descubierto porque un simple
        # guardado de configuración tardaba ~24s (6 invalidaciones de caché x
        # ~4s cada una). El código ya está diseñado para degradar sin Redis
        # (ver apps/core/cache_utils.py y apps/core/throttling.py); esto hace
        # que esa degradación sea rápida (ms) en vez de lenta (segundos).
        'OPTIONS': {
            'socket_connect_timeout': float(os.getenv('REDIS_CONNECT_TIMEOUT', '0.05')),
            'socket_timeout': float(os.getenv('REDIS_SOCKET_TIMEOUT', '0.05')),
        },
    },
}

# TTLs específicos para distintos tipos de contenido cacheable
CACHE_TTL = {
    'catalogo_productos': int(os.getenv('CACHE_TTL_CATALOGO', '300')),
    'configuraciones': int(os.getenv('CACHE_TTL_CONFIG', '600')),
    'parametros_fiscales': int(os.getenv('CACHE_TTL_FISCAL', '900')),
    'dashboard': int(os.getenv('CACHE_TTL_DASHBOARD', '120')),
}

# --- Seguridad: bloqueo por intentos fallidos de login (Zero Trust) ---
LOGIN_MAX_INTENTOS = int(os.getenv('LOGIN_MAX_INTENTOS', '5'))
LOGIN_VENTANA_MINUTOS = int(os.getenv('LOGIN_VENTANA_MINUTOS', '15'))

# --- Fiscal multi-país ---
# Último recurso cuando un tenant no tiene `ConfiguracionEmpresa.pais_codigo`
# configurado (no debería ocurrir tras el seeding de TenantService, pero se
# declara explícito en vez de caer en silencio a 'VE' dentro del código).
DEFAULT_TAX_COUNTRY = os.getenv('DEFAULT_TAX_COUNTRY', 'VE')

# Configuración de Celery
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# =========================================================
# SPECTACULAR (Swagger / OpenAPI 3)
# =========================================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'ERP SaaS API Documentación',
    'DESCRIPTION': (
        'API del ERP SaaS Multi-Tenant. Gestiona Inventario, Facturación '
        'conforme a las providencias del SENIAT, RRHH, Pagos y Reportes.\n\n'
        '**Autenticación:** Bearer token (JWT). Obtén un par access/refresh '
        'en `/api/v1/auth/token/`.'
    ),
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'URLCONF': None,
    'SCHEMA_PATH_PREFIX': r'/api/v1/',
    'COMPONENT_SPLIT_PATCH': True,
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'auth', 'description': 'Autenticación, registro y gestión de usuarios del tenant.'},
        {'name': 'clientes', 'description': 'CRUD de clientes del tenant.'},
        {'name': 'configuracion', 'description': 'Configuración de empresa, IVA y tipos de documento fiscal.'},
        {'name': 'facturacion', 'description': 'Facturación SENIAT, órdenes, pagos y pública.'},
        {'name': 'inventario', 'description': 'Productos, variantes, categorías, almacenes y stock.'},
        {'name': 'proveedores', 'description': 'CRUD de proveedores del tenant.'},
        {'name': 'pagos', 'description': 'Métodos de pago, Pago Móvil, Zelle y pasarelas.'},
        {'name': 'reportes', 'description': 'Reportes de ventas, clientes, dashboard y cierre de caja.'},
        {'name': 'rrhh', 'description': 'Asistencia, horarios, sucursales y días festivos.'},
        {'name': 'public', 'description': 'Catálogo público y pedidos de clientes finales.'},
        {'name': 'tenants', 'description': 'Gestión de inquilinos, planes y suscripciones (esquema público).'},
    ],
    'TAG_REGEX': r'^/(api/v1/)?(?P<tag>[a-z-]+)/',  # Agrupa automáticamente por el primer segmento
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
        'displayOperationId': False,
        'filter': True,
        'deepLinking': True,
        'docExpansion': 'none',
    },
    'SECURITY': [
        {'jwtAuth': []},
    ],
}
