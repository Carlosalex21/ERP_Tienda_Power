#!/bin/sh
set -e

#esperar base de datos
python wait-for-db.py

chown -R www-data:www-data /app/media

# Ejecutar migraciones
echo "Applying database migrations..."
python manage.py migrate --noinput

# Iniciar supervisord (que a su vez iniciará gunicorn y nginx)
echo "INICIANDO BUILD V3 - ESTE ES EL CORRECTO"
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf