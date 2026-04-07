FROM python:3.12-slim

WORKDIR /app

# System deps: libpq for psycopg, gcc for native extensions, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv

# ── Install app dependencies ────────────────────────────────────────────────
# Embeddings are now handled by the remote API (httpx) — no more torch/sentence-transformers.
COPY pyproject.toml .
RUN uv pip install --system --no-cache \
    "django>=5.2,<7" \
    "psycopg[binary]>=3.2" \
    "pgvector>=0.3" \
    "django-mcp-server>=0.5" \
    "markdown>=3.7" \
    "python-dotenv>=1.0" \
    "dj-database-url>=2.0" \
    "whitenoise>=6.8" \
    "httpx>=0.27" \
    "gunicorn"

# ── Copy application source and collect static files ─────────────────────────
COPY . .
RUN python manage.py collectstatic --noinput

# Create a non-root user and transfer ownership
RUN useradd -m -u 1000 nexus && chown -R nexus:nexus /app
USER nexus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "120"]
