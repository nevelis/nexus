"""Embedding generation via the remote embeddings API.

Replaces the previous sentence-transformers local model with HTTP calls to the
embeddings microservice. The client is configured via EMBEDDINGS_API_URL env var
and supports batch chunking for large input sets.
"""

import logging
import os
from itertools import islice

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_API_URL = "http://embeddings.embeddings.svc.cluster.local:8000/embed"
LOCAL_DEV_URL = "https://embeddings.lab.amazingland.live/embed"

EMBEDDINGS_API_URL = os.environ.get("EMBEDDINGS_API_URL", "")
DEFAULT_TIMEOUT = 5.0
DEFAULT_BATCH_SIZE = 50


# ── Exceptions ───────────────────────────────────────────────────────────────


class EmbeddingServiceError(Exception):
    """Raised when the embeddings API is unreachable or returns an error."""


# ── Client ───────────────────────────────────────────────────────────────────


class EmbeddingClient:
    """HTTP client for the remote embeddings API.

    Args:
        api_url: Full URL to the /embed endpoint. Resolved from EMBEDDINGS_API_URL
                 env var, falling back to in-cluster default or local dev URL.
        timeout: Request timeout in seconds (default 5).
        batch_size: Maximum texts per request (default 50).
    """

    def __init__(
        self,
        api_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.api_url = api_url or _resolve_api_url()
        self.timeout = timeout
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Automatically chunks into batches of `batch_size` texts per request.

        Args:
            texts: List of strings to embed.

        Returns:
            List of 384-dimensional float vectors, one per input text.

        Raises:
            EmbeddingServiceError: If the API is unreachable or returns an error.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        it = iter(texts)
        while True:
            batch = list(islice(it, self.batch_size))
            if not batch:
                break
            all_embeddings.extend(self._embed_batch(batch))
        return all_embeddings

    def embed_one(self, text: str) -> list[float]:
        """Generate a single embedding vector.

        Args:
            text: String to embed.

        Returns:
            384-dimensional float vector.

        Raises:
            EmbeddingServiceError: If the API is unreachable or returns an error.
        """
        results = self.embed([text])
        return results[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Send a single batch to the API."""
        try:
            response = httpx.post(
                self.api_url,
                json={"text": texts},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]
        except httpx.TimeoutException as exc:
            raise EmbeddingServiceError(
                f"Embeddings API timed out after {self.timeout}s: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingServiceError(
                f"Embeddings API returned {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingServiceError(f"Embeddings API request failed: {exc}") from exc
        except (KeyError, ValueError) as exc:
            raise EmbeddingServiceError(
                f"Embeddings API returned unexpected response: {exc}"
            ) from exc


# ── Module-level singleton & convenience function ────────────────────────────

_client: EmbeddingClient | None = None


def _resolve_api_url() -> str:
    """Resolve the API URL from env var, with fallback logic."""
    if EMBEDDINGS_API_URL:
        return EMBEDDINGS_API_URL
    # In-cluster default; fall back to public URL for local dev
    debug = os.environ.get("DEBUG", "True") == "True"
    return LOCAL_DEV_URL if debug else DEFAULT_API_URL


def get_client() -> EmbeddingClient:
    """Get or create the module-level singleton client."""
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client


def generate_embedding(text: str) -> list[float] | None:
    """Generate a 384-dimensional embedding vector for the given text.

    This is the drop-in replacement for the old sentence-transformers function.
    Returns None if embedding generation fails, so callers can fall back to
    keyword search.
    """
    try:
        return get_client().embed_one(text)
    except EmbeddingServiceError as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None
