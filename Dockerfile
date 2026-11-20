FROM python:3.11-slim

# Instalar uv directamente
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY . .

# Instalamos el paquete (sin -e porque es un contenedor de producción)
RUN uv pip install --system .

EXPOSE 8501