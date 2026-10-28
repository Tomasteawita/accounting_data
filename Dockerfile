FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instalar dependencias mínimas del sistema y crear usuario no-root (UID/GID 1000)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appgroup && useradd -u 1000 -g appgroup -d /app -s /sbin/nologin appuser

# Instalar dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto y preparar directorio de estáticos
COPY . /app/
RUN mkdir -p /app/staticfiles && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Optimizado para AWS EC2 t4g.small (2 vCPU ARM64, 2GB RAM):
# 2 workers + 2 threads y reciclaje de workers para prevenir fugas de memoria
CMD ["gunicorn", "accounting_data.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--max-requests", "500", "--max-requests-jitter", "50"]
