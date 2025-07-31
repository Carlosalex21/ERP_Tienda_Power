# Usar una imagen base oficial y estable de Python
FROM python:3.11-slim

# Instalar Nginx y dependencias (¡falta en tu Dockerfile!)
RUN apt-get update && apt-get install -y \
    nginx \
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

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN python manage.py collectstatic --noinput

EXPOSE 8000
EXPOSE 80

CMD ["/entrypoint.sh"]