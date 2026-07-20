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
# Para depuración, permitimos todos los hosts. Esto elimina cualquier conflicto
# con el middleware de tenants. En producción, esto debe ser más restrictivo.
ALLOWED_HOSTS = ['*']


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
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
    "corsheaders",

    # App para gestionar los subdominios y suscripciones
    'apps.tenants', 
]

# Aplicaciones del Inquilino (Esquema 'cliente1', 'cliente2')
TENANT_APPS = [
    "django.contrib.auth", # Permite que cada cliente tenga sus propios usuarios
    "django.contrib.contenttypes",

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

# --- Configuración de CORS ---
# En desarrollo, puedes usar CORS_ALLOW_ALL_ORIGINS = True para simplicidad.
# En producción, se recomienda ponerlo en False y usar una de las siguientes opciones.
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'True') == 'True'

# Esta es la forma automática y segura de permitir todos tus subdominios en producción.
TENANT_DOMAIN_CLEAN = os.getenv('TENANT_DOMAIN', 'localhost').split(':')[0] # 'localhost:8000' -> 'localhost'
CORS_ALLOWED_ORIGIN_REGEXES = [
    # Permite el frontend de desarrollo
    r"^http://localhost:3000\Z",
    r"^http://127.0.0.1:3000\Z",
    # Permite todos los subdominios de tu dominio de tenants
    r"^https?://\w+\.{}\Z".format(TENANT_DOMAIN_CLEAN),
]


CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
X_FRAME_OPTIONS = 'SAMEORIGIN'

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
            'PASSWORD': os.getenv('DB_PASSWORD', "carlosalex"), # CAMBIARLO POR PASSWORD LOCAL
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

# Configuración de Celery
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'


SPECTACULAR_SETTINGS = {
    'TITLE': 'ERP SaaS API Documentación',
    'DESCRIPTION': 'Gestión de Inventario, Facturación y RRHH.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'URLCONF': None, 
    'SCHEMA_PATH_PREFIX': r'/api/v1/',
    'COMPONENT_SPLIT_PATCH': True,
    'COMPONENT_SPLIT_REQUEST': True,
    # Configuramos el comportamiento del Swagger UI
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,  # Mantiene el token aunque recargue el navegador
        'displayOperationId': False,
        'filter': True,                # Añade una barra de búsqueda rapida para endpoints
    },
}