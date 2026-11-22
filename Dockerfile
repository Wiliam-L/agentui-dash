# ── Stage 1: Build dependencies ────────────────────────────────
FROM ghcr.io/astral-sh/uv:latest AS builder

WORKDIR /src
COPY pyproject.toml app_base/ agentui_mcp/ ./
RUN uv venv && uv pip install .

# ── Stage 2: Runtime ───────────────────────────────────────────
FROM python:3.11-slim

# System deps for kaleido (webkit) and weasyprint (pango)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libglib2.0-0 libwebkit2gtk-4.1 libpango-1.0-0 libgdk-pixbuf2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual env from the builder
COPY --from=builder /src/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml ./
COPY app_base/ app_base/
COPY agentui_mcp/ agentui_mcp/

# Non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/')" || exit 1