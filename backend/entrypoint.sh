#!/bin/sh
set -e

chown -R www-data:www-data /app/media
chown -R www-data:www-data /app/logs

# Ejecutar migraciones
echo "Applying database migrations..."
python manage.py migrate --noinput

# Iniciar supervisord (que a su vez iniciará gunicorn y nginx)
echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf