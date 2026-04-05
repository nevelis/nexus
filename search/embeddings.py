"""Embedding generation using sentence-transformers (local, no API key required).

The model is lazy-loaded and cached as a module-level singleton — it's loaded
once on first use and reused for every subsequent call within the same process.
The model is baked into the Docker image at build time so there's no cold-start
download in production.
"""
import logging

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def _get_model():
    """Lazy-load and cache the SentenceTransformer model (loaded once per process)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def generate_embedding(text: str) -> list[float] | None:
    """Generate a 384-dimensional embedding vector for the given text.

    Returns None if embedding generation fails (e.g. during testing or if the
    model fails to load). Callers should gracefully handle None by falling back
    to keyword search.
    """
    try:
        model = _get_model()
        return model.encode(text).tolist()
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None
