from pathlib import Path
import os
from datetime import timedelta
import dj_database_url

# Import dotenv
from dotenv import load_dotenv # type: ignore
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")

# En producción (Coolify), DEBUG será 'False'.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# En Coolify, pondrás tu dominio aquí, ej: "www.tusitio.com,tusitio.com"
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

# =========================================================
# CONFIGURACIÓN MULTI-TENANT (django-tenants)
# =========================================================

# Aplicaciones Compartidas (Esquema 'public')
SHARED_APPS = [
    'django_tenants', 

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
    'apps.facturacion',
    'apps.rrhh',
    'apps.reportes',
    
    # Si 'erp' y 'tienda' aún tienen modelos viejos, déjalos aquí temporalmente
    #'erp',
    #'tienda',
]
INSTALLED_APPS = list(set(SHARED_APPS + TENANT_APPS))

# Definición de modelos para Tenants y Dominios
TENANT_MODEL = "tenants.Client"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# Enrutador de base de datos
DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware", 
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Para servir archivos estáticos en producción
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    #"django.middleware.csrf.CsrfViewMiddleware", temporalmente comentado
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:8080,http://127.0.0.1:8080').split(',')
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:8080').split(',')
X_FRAME_OPTIONS = 'SAMEORIGIN'
ROOT_URLCONF = "backend.urls"

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


# =========================================================
# BASE DE DATOS (Multi-Tenant)
# =========================================================

if 'DATABASE_URL' in os.environ:
    # Producción (Coolify)
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=False)
    }
    # Forzamos el motor de tenants para la URL de producción
    DATABASES['default']['ENGINE'] = 'django_tenants.postgresql_backend'
else:
    # Desarrollo Local
    DATABASES = {
        'default': {
            'ENGINE': 'django_tenants.postgresql_backend', 
            'NAME': 'emp_system_saas', # 
            'USER': 'postgres',
            'PASSWORD': 'carlosalex', # CAMBIARLO POR PASSWORD LOCAL
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

# Local Settings override
try:
    from .local_settings import *
except ImportError:
    pass