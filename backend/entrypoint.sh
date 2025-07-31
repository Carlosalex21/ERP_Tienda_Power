#!/bin/bash
set -e

# Ejecutar migraciones (opcional pero recomendado)
python manage.py migrate --noinput

# Lanzar Gunicorn en background
gunicorn backend.wsgi --bind 0.0.0.0:8000 &

# Lanzar Nginx en foreground
nginx -g "daemon off;"