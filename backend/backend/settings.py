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
#DEBUG = os.getenv('DEBUG', 'False') == 'True'
DEBUG = True

# --- Configuración de ALLOWED_HOSTS para Multi-Tenancy ---
# Para depuración, permitimos todos los hosts. Esto elimina cualquier conflicto
# con el middleware de tenants. En producción, esto debe ser más restrictivo.
ALLOWED_HOSTS = ['*']


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
        'rest_framework_simplejwt.authentication.JWTAuthentication',
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
    #'EXCEPTION_HANDLER': 'apps.core.exception_handler.custom_exception_handler',

    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        # En desarrollo subimos los límites para no bloquear operaciones simultáneas
        # del panel (dashboard + POS + inventario). En producción se ajustan vía env.
        'anon': os.getenv('THROTTLE_ANON', '120/min'),
        'user': os.getenv('THROTTLE_USER', '1000/min'),
        'login': os.getenv('THROTTLE_LOGIN', '20/min'),
        'catalogo': os.getenv('THROTTLE_CATALOGO', '300/min'),
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
    'apps.configuracion',
    'apps.clientes',
    'apps.proveedores',
    'apps.inventario',
    'apps.pagos', # Nueva app de pagos
    'apps.facturacion',
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
    "django.middleware.common.CommonMiddleware",
    #"django.middleware.csrf.CsrfViewMiddleware", temporalmente comentado
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
    DATABASES = {
        'default': {
            'ENGINE': 'django_tenants.postgresql_backend',
            'NAME': 'emp_system_saas', # 
            'USER': 'postgres',
            'PASSWORD': os.getenv('DB_PASSWORD', "carlosalex21"), # CAMBIARLO POR PASSWORD LOCAL
            'HOST': 'localhost',
            'PORT': '5432',
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
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'erp-local-cache',
    },
    'redis_cache': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'erp_saas',
        'TIMEOUT': int(os.getenv('CACHE_TIMEOUT', '300')),
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
