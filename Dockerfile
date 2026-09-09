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

# Kilitli bağımlılıkları önce kopyala (Docker cache ve tekrarlanabilir build)
COPY api/requirements.lock.txt /build/requirements.lock.txt

# Sanal ortama kur (final imaja sadece /venv kopyalanır)
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock.txt

# --- Aşama 2: Runtime ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# Türkçe font desteği (PDF rapor oluşturma için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app

# Sadece virtual env'i builder'dan kopyala
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Uygulama kodunu kopyala (tests/, .venv/, archieve/ dışarıda kalır → .dockerignore)
COPY --chown=app:app api/ /app/api/
COPY --chown=app:app scripts/ /app/scripts/
RUN mkdir -p "/app/2026 TGTC"
COPY --chown=app:app ["2026 TGTC/tgtc_2026_full_database.json", "/app/2026 TGTC/tgtc_2026_full_database.json"]
COPY --chown=app:app ["2026 TGTC/tgtc_2026_rules_and_notes.json", "/app/2026 TGTC/tgtc_2026_rules_and_notes.json"]

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

EXPOSE 8080

# Yerel Docker sağlık kontrolü; Cloud Run ayrıca HTTP probe'ları kullanır.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.getenv('PORT','8080'), timeout=5)"

# Multi-core uvicorn: Cloud Run 2 CPU → 4 worker (2*CPU + 1 formülü)
# WEB_CONCURRENCY env var ile Cloud Run'dan override edilebilir
USER app
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-2}"]
