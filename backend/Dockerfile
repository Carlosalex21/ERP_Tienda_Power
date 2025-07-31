# Usar una imagen base oficial y estable de Python
FROM python:3.11-slim

# Instala Nginx, Supervisor y las dependencias de WeasyPrint
RUN apt-get update && apt-get install -y \
    nginx \
    supervisor \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copia los archivos de configuración
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Ejecuta las migraciones y recolecta estáticos
RUN python manage.py migrate --noinput
RUN python manage.py collectstatic --noinput

EXPOSE 80

# El comando final ahora es supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]