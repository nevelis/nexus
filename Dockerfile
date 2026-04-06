FROM python:3.12-slim

WORKDIR /app

# System deps: libpq for psycopg, gcc for native extensions, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv

# ── Pre-install heavy ML deps (torch + sentence-transformers) ────────────────
# These are installed BEFORE COPY pyproject.toml so this layer is cached even
# when app code or pyproject.toml changes. torch is ~1.5GB — keeping it in a
# stable layer means CI builds only re-install the fast lightweight deps on
# most commits.
#
# Pin to a minor version range so the cache only busts on intentional bumps.
RUN uv pip install --system --no-cache "sentence-transformers>=3.0,<4"

# ── Bake the embedding model into the image ──────────────────────────────────
# Model is downloaded once at build time; pods start instantly with no
# cold-start download. HF_HOME is inside /app so the nexus user owns it.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ── Remaining lightweight app deps ───────────────────────────────────────────
# Separate COPY so Docker can cache this layer when only source files change.
# sentence-transformers is already installed; uv resolves and skips it.
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
