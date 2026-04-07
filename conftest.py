"""
Root pytest configuration.

Mocks embedding generation globally so tests never call the remote API.
All tests default to the keyword-fallback code path. Tests that specifically
need to exercise the embedding client mock it at the EmbeddingClient level.
"""

import pytest


@pytest.fixture(autouse=True)
def mock_embeddings(monkeypatch):
    """Replace generate_embedding with a no-op that returns None.

    This keeps tests fast and database-agnostic: with None, all search
    falls back to keyword matching, which works with both SQLite and Postgres.
    Any test that needs a real embedding vector can override this fixture.
    """
    monkeypatch.setattr("search.embeddings.generate_embedding", lambda text: None)
