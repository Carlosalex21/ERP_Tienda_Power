#!/bin/sh
set -e

# Ejecutar migraciones
echo "Applying database migrations..."
python manage.py migrate --noinput

# Iniciar supervisord (que a su vez iniciará gunicorn y nginx)
echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf