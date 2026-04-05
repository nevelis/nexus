FROM python:3.12-slim

WORKDIR /app

# System deps: libpq for psycopg, gcc for native extensions, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN pip install uv

# Install Python dependencies before copying app code (better layer caching)
COPY pyproject.toml .
RUN uv pip install --system --no-cache -e "."

# ── Bake in the sentence-transformers model ────────────────────────────────
# The model is downloaded once at image build time so pods start instantly
# with no cold-start download. HF_HOME is set to a path inside /app so it's
# owned by the nexus user created below.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy application code
COPY . .

# Collect static files (whitenoise serves them; needs SECRET_KEY default in settings)
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
