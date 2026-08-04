# ==============================================================================
# GTİP Tespit Karar Destek Sistemi - Multi-Stage Production Dockerfile
# Aşama 1 (builder): Bağımlılıklar kurulur, gereksiz araçlar final imaja girmez.
# Aşama 2 (runtime): Sadece uygulama kodu ve kurulu paketler kopyalanır (~slim).
# ==============================================================================

# --- Aşama 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /build

# Sistem bağımlılıkları (sadece derleme için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Önce requirements.txt kopyala (Docker cache katmanı optimizasyonu)
COPY api/requirements.txt /build/requirements.txt

# Sanal ortama kur (final imaja sadece /venv kopyalanır)
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

# --- Aşama 2: Runtime ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# Türkçe font desteği (PDF rapor oluşturma için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Sadece virtual env'i builder'dan kopyala
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Uygulama kodunu kopyala (tests/, .venv/, archieve/ dışarıda kalır → .dockerignore)
COPY api/ /app/api/
COPY scripts/ /app/scripts/

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Cloud Run sağlık kontrolü (cold start tespiti için)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/v1/health || exit 1

# Multi-core uvicorn: Cloud Run 2 CPU → 4 worker (2*CPU + 1 formülü)
# WEB_CONCURRENCY env var ile Cloud Run'dan override edilebilir
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-4} --loop uvloop --http h11"]
