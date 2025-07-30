# Usar una imagen base oficial y estable de Python
FROM python:3.11-slim

# Establecer variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# PASO CLAVE: Instalar las dependencias de sistema para WeasyPrint y PostgreSQL
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de requerimientos e instalar los paquetes de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código de la aplicación al contenedor
COPY . .

# Indicar que la aplicación escuchará en el puerto 8000
EXPOSE 8000

# Comando para iniciar la aplicación al arrancar el contenedor
CMD ["gunicorn", "backend.wsgi", "--bind", "0.0.0.0:8000"]