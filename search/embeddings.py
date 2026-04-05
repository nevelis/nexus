"""Embedding generation via OpenAI (swappable for local models)."""
from django.conf import settings


def generate_embedding(text: str) -> list[float] | None:
    """Generate a vector embedding for the given text.

    Returns None if no API key is configured.
    """
    if not settings.OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Embedding generation failed: %s", e)
        return None
