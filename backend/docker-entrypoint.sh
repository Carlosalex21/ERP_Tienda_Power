#!/bin/sh
# Punto de entrada del contenedor backend. Recibe como $1 el rol a cumplir
# ("web" o "celery", ver CMD en el Dockerfile y `command:` en
# docker-compose.prod.yml) -- las migraciones y `collectstatic` solo corren
# UNA vez, desde el contenedor "web", para evitar que dos réplicas (o el
# worker de Celery arrancando en paralelo) compitan por aplicar la misma
# migración a la vez.
#
# "web" corre Daphne (servidor ASGI), no Gunicorn (WSGI) -- necesario para
# los WebSockets de Channels (ver `backend/asgi.py` y
# `apps.restaurantes.consumers`). Daphne sirve HTTP normal exactamente igual
# que antes (Django adapta las vistas síncronas por debajo), así que este
# cambio no debería notarse para nada que no sea WebSockets.
set -e

esperar_base_de_datos() {
    echo "Esperando a que la base de datos esté lista..."
    python <<'PYEOF'
import os
import sys
import time

import psycopg2

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("DATABASE_URL no está definida -- se omite la espera.")
    sys.exit(0)

for intento in range(1, 31):
    try:
        conn = psycopg2.connect(url)
        conn.close()
        print("Base de datos lista.")
        sys.exit(0)
    except psycopg2.OperationalError as exc:
        print(f"  intento {intento}/30: {exc}".strip())
        time.sleep(2)

print("No se pudo conectar a la base de datos a tiempo.", file=sys.stderr)
sys.exit(1)
PYEOF
}

ROL="${1:-web}"

esperar_base_de_datos

if [ "$ROL" = "web" ]; then
    echo "Aplicando migraciones del esquema compartido (--shared)..."
    python manage.py migrate_schemas --shared --noinput

    echo "Recolectando archivos estáticos..."
    python manage.py collectstatic --noinput --clear

    echo "Iniciando Daphne (ASGI: HTTP + WebSockets)..."
    exec daphne \
        --bind 0.0.0.0 \
        --port 8000 \
        --access-log - \
        backend.asgi:application

elif [ "$ROL" = "celery" ]; then
    echo "Iniciando worker de Celery..."
    exec celery -A backend worker --loglevel=info --concurrency="${CELERY_CONCURRENCY:-2}"

elif [ "$ROL" = "celery-beat" ]; then
    # Planificador de tareas periódicas -- el "reloj" que dispara las tareas
    # con `CELERY_BEAT_SCHEDULE` (ver `backend/settings.py`) a la hora que
    # les toca; el trabajo real lo sigue ejecutando el worker de arriba
    # (celery-beat solo encola, nunca ejecuta la tarea él mismo). Usa el
    # scheduler de archivo (no `django_celery_beat`, que requiere un modelo
    # de DB pensado para un solo schema) -- el horario vive en código, no en
    # una tabla, lo cual encaja mejor con un sistema multi-tenant donde la
    # tarea misma decide a qué tenants les toca algo.
    # `--schedule` en `/tmp` (no en `/app`, el directorio de trabajo): el
    # contenedor corre como usuario `django` (uid 1000, no root -- ver
    # Dockerfile) y `/app` no le pertenece, así que Celery no puede crear
    # ahí su archivo de estado `celerybeat-schedule` y el proceso queda en
    # crash-loop por "Permission denied". `/tmp` siempre es escribible.
    echo "Iniciando Celery Beat (planificador de tareas periódicas)..."
    exec celery -A backend beat --loglevel=info --pidfile= --schedule=/tmp/celerybeat-schedule

else
    echo "Rol desconocido: $ROL (usa 'web', 'celery' o 'celery-beat')" >&2
    exit 1
fi
