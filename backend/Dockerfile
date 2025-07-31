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

# Copia los archivos de configuración y el nuevo entrypoint
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Crea la carpeta para los archivos media (imágenes)
RUN mkdir -p /app/media

# Recolecta estáticos (esto sí se puede hacer durante el build)
RUN python manage.py collectstatic --noinput

# Expone el puerto 80 (para Nginx)
EXPOSE 80

# El comando final ahora es el entrypoint
CMD ["/entrypoint.sh"]
