# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Etapa 1: builder -- instala dependencias Python (algunas necesitan
# compilar contra headers de sistema que NO deben quedar en la imagen final).
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo requirements primero: si el código cambia pero las
# dependencias no, Docker reusa esta capa entera en el siguiente build.
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Etapa 2: runtime -- imagen final, sin compiladores ni headers de build.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/django/.local/bin:$PATH

WORKDIR /app

# Librerías de sistema en runtime:
#   - libpq5: cliente Postgres (psycopg2-binary las trae empaquetadas, pero
#     libpq5 asegura compatibilidad si el wheel las busca dinámicamente).
#   - libpango/libcairo/libgdk-pixbuf/shared-mime-info: requeridas por
#     WeasyPrint para renderizar los PDFs de factura.
#   - curl: usado por el HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    shared-mime-info \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 django

COPY --from=builder --chown=django:django /root/.local /home/django/.local
COPY --chown=django:django . .

RUN mkdir -p /app/staticfiles /app/media && chown -R django:django /app/staticfiles /app/media

USER django

EXPOSE 8000

# `/admin/login/` existe tanto en `urls_public` como en `urls_tenants` (ver
# `backend/urls_public.py` / `urls_tenants.py`) y responde 200 sin sesión,
# así que el healthcheck funciona sin importar qué esquema resuelva
# django-tenants para el Host `127.0.0.1` que usa curl desde dentro del
# contenedor (no coincide con ningún dominio de tenant real).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/admin/login/ -o /dev/null || exit 1

# Invocado con `sh` explícito (en vez de depender del bit ejecutable del
# archivo, que Windows/git no preservan de forma confiable en el contexto
# de build).
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
# "web" = Daphne (ASGI: HTTP + WebSockets) -- ver `docker-entrypoint.sh`.
CMD ["web"]
