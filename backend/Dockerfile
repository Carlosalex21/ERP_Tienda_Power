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

# Establece variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia el archivo de requerimientos e instala los paquetes de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación al contenedor
COPY . .

# Copia los archivos de configuración
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# --- CAMBIOS IMPORTANTES ---
# 1. Crea la carpeta para los archivos media (imágenes)
RUN mkdir -p /app/media

# 2. Ejecuta las migraciones y recolecta estáticos durante la construcción
RUN python manage.py migrate --noinput
RUN python manage.py collectstatic --noinput
# -------------------------

# Expone el puerto 80 (para Nginx)
EXPOSE 80

# El comando final ahora es supervisord (ya no se usa entrypoint.sh)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
