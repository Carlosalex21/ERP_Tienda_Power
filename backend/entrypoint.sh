#!/bin/sh
set -e

echo "Adjusting permissions for media volume..."
chown -R www-data:www-data /app/media

# Ejecutar migraciones
echo "Applying database migrations..."
python manage.py migrate --noinput

# Iniciar supervisord (que a su vez iniciará gunicorn y nginx)
echo "Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf