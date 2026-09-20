#!/bin/sh
# Punto de entrada del contenedor backend. Recibe como $1 el rol a cumplir
# ("gunicorn" o "celery", ver CMD en el Dockerfile y `command:` en
# docker-compose.prod.yml) -- las migraciones y `collectstatic` solo corren
# UNA vez, desde el contenedor "gunicorn", para evitar que dos réplicas (o
# el worker de Celery arrancando en paralelo) compitan por aplicar la misma
# migración a la vez.
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

ROL="${1:-gunicorn}"

esperar_base_de_datos

if [ "$ROL" = "gunicorn" ]; then
    echo "Aplicando migraciones del esquema compartido (--shared)..."
    python manage.py migrate_schemas --shared --noinput

    echo "Recolectando archivos estáticos..."
    python manage.py collectstatic --noinput --clear

    echo "Iniciando Gunicorn..."
    exec gunicorn backend.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-3}" \
        --timeout "${GUNICORN_TIMEOUT:-60}" \
        --access-logfile - \
        --error-logfile -

elif [ "$ROL" = "celery" ]; then
    echo "Iniciando worker de Celery..."
    exec celery -A backend worker --loglevel=info --concurrency="${CELERY_CONCURRENCY:-2}"

else
    echo "Rol desconocido: $ROL (usa 'gunicorn' o 'celery')" >&2
    exit 1
fi
