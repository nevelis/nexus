"""Tests for the search app: EmbeddingClient, generate_embedding, and search view."""

from unittest.mock import patch

from django.test import Client, TestCase

import search.embeddings as emb
from documents.models import Document
from search.embeddings import EmbeddingClient, EmbeddingServiceError

# Capture the real generate_embedding function *at module import time*, before
# the conftest autouse fixture replaces the module attribute with a no-op lambda.
_real_generate_embedding = emb.generate_embedding


# ── EmbeddingClient unit tests ──────────────────────────────────────────────


class TestEmbeddingClient(TestCase):
    """Tests for EmbeddingClient HTTP calls."""

    def _make_client(self, **kwargs):
        return EmbeddingClient(api_url="https://test.example.com/embed", **kwargs)

    @patch("search.embeddings.httpx.post")
    def test_embed_returns_list_of_vectors(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "embeddings": [[0.1] * 384, [0.2] * 384],
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384,
        }
        client = self._make_client()
        result = client.embed(["hello", "world"])
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), 384)
        self.assertTrue(all(isinstance(v, float) for v in result[0]))

    @patch("search.embeddings.httpx.post")
    def test_embed_one_returns_single_vector(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "embeddings": [[0.5] * 384],
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384,
        }
        client = self._make_client()
        result = client.embed_one("hello world")
        self.assertEqual(len(result), 384)

    @patch("search.embeddings.httpx.post")
    def test_embed_sends_correct_payload(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"embeddings": [[0.1] * 384]}
        client = self._make_client()
        client.embed(["test text"])
        mock_post.assert_called_once_with(
            "https://test.example.com/embed",
            json={"text": ["test text"]},
            timeout=5.0,
        )

    @patch("search.embeddings.httpx.post")
    def test_embed_empty_list_returns_empty(self, mock_post):
        client = self._make_client()
        result = client.embed([])
        self.assertEqual(result, [])
        mock_post.assert_not_called()

    @patch("search.embeddings.httpx.post")
    def test_batch_chunking(self, mock_post):
        """Texts exceeding batch_size are split into multiple requests."""
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        # Each call returns embeddings for batch_size items
        mock_post.return_value.json.side_effect = [
            {"embeddings": [[0.1] * 384] * 3},
            {"embeddings": [[0.2] * 384] * 2},
        ]
        client = self._make_client(batch_size=3)
        result = client.embed(["a", "b", "c", "d", "e"])
        self.assertEqual(len(result), 5)
        self.assertEqual(mock_post.call_count, 2)

    @patch("search.embeddings.httpx.post")
    def test_timeout_raises_embedding_service_error(self, mock_post):
        import httpx

        mock_post.side_effect = httpx.ReadTimeout("timed out")
        client = self._make_client()
        with self.assertRaises(EmbeddingServiceError) as ctx:
            client.embed(["test"])
        self.assertIn("timed out", str(ctx.exception))

    @patch("search.embeddings.httpx.post")
    def test_http_error_raises_embedding_service_error(self, mock_post):
        import httpx

        response = httpx.Response(
            500, text="Internal Server Error", request=httpx.Request("POST", "http://test")
        )
        mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=response.request, response=response
        )
        client = self._make_client()
        with self.assertRaises(EmbeddingServiceError) as ctx:
            client.embed(["test"])
        self.assertIn("500", str(ctx.exception))

    @patch("search.embeddings.httpx.post")
    def test_connection_error_raises_embedding_service_error(self, mock_post):
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")
        client = self._make_client()
        with self.assertRaises(EmbeddingServiceError):
            client.embed(["test"])

    @patch("search.embeddings.httpx.post")
    def test_bad_response_format_raises_embedding_service_error(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"wrong_key": []}
        client = self._make_client()
        with self.assertRaises(EmbeddingServiceError):
            client.embed(["test"])


# ── generate_embedding convenience function ──────────────────────────────────


class TestGenerateEmbedding(TestCase):
    """Tests for the module-level generate_embedding wrapper."""

    @patch("search.embeddings.httpx.post")
    def test_returns_list_of_floats(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {
            "embeddings": [[1.0] * 384],
        }
        # Reset singleton to pick up fresh client
        emb._client = None
        try:
            result = _real_generate_embedding("hello world")
        finally:
            emb._client = None
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 384)
        self.assertTrue(all(isinstance(v, float) for v in result))

    @patch("search.embeddings.httpx.post")
    def test_returns_none_on_api_failure(self, mock_post):
        import httpx

        mock_post.side_effect = httpx.ConnectError("Connection refused")
        emb._client = None
        try:
            result = _real_generate_embedding("test")
        finally:
            emb._client = None
        self.assertIsNone(result)

    def test_returns_none_on_embedding_service_error(self):
        """generate_embedding catches EmbeddingServiceError and returns None."""
        with patch.object(emb, "get_client") as mock_get:
            mock_get.return_value.embed_one.side_effect = EmbeddingServiceError("API down")
            result = _real_generate_embedding("test")
        self.assertIsNone(result)


# ── URL resolution ───────────────────────────────────────────────────────────


class TestApiUrlResolution(TestCase):
    """Tests for API URL resolution logic."""

    def test_env_var_takes_precedence(self):
        with patch.object(emb, "EMBEDDINGS_API_URL", "https://custom.example.com/embed"):
            url = emb._resolve_api_url()
        self.assertEqual(url, "https://custom.example.com/embed")

    def test_debug_mode_uses_local_dev_url(self):
        with (
            patch.object(emb, "EMBEDDINGS_API_URL", ""),
            patch.dict("os.environ", {"DEBUG": "True"}),
        ):
            url = emb._resolve_api_url()
        self.assertEqual(url, emb.LOCAL_DEV_URL)

    def test_production_uses_cluster_url(self):
        with (
            patch.object(emb, "EMBEDDINGS_API_URL", ""),
            patch.dict("os.environ", {"DEBUG": "false"}),
        ):
            url = emb._resolve_api_url()
        self.assertEqual(url, emb.DEFAULT_API_URL)


# ── Semantic search view ─────────────────────────────────────────────────────


class TestSemanticSearchView(TestCase):
    """Tests for /search/ endpoint.

    conftest mocks generate_embedding → None, so all searches use keyword fallback.
    """

    def setUp(self):
        self.client = Client()
        Document.objects.create(
            title="Django Tutorial",
            body="Learn to build web apps with Django",
            status="published",
        )
        Document.objects.create(
            title="Python Basics",
            body="Introduction to Python programming",
            status="published",
        )

    def test_requires_query_param(self):
        response = self.client.get("/search/")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    def test_returns_200_with_query(self):
        response = self.client.get("/search/?q=Django")
        self.assertEqual(response.status_code, 200)

    def test_results_in_response(self):
        response = self.client.get("/search/?q=Django")
        data = response.json()
        self.assertIn("results", data)

    def test_keyword_fallback_finds_matching_doc(self):
        response = self.client.get("/search/?q=Django")
        data = response.json()
        titles = [r["title"] for r in data["results"]]
        self.assertIn("Django Tutorial", titles)

    def test_query_echoed_in_response(self):
        response = self.client.get("/search/?q=myquery")
        data = response.json()
        self.assertEqual(data["query"], "myquery")

    def test_limit_param_respected(self):
        response = self.client.get("/search/?q=Python&limit=1")
        data = response.json()
        self.assertLessEqual(len(data["results"]), 1)

    def test_result_includes_required_fields(self):
        response = self.client.get("/search/?q=Django")
        data = response.json()
        for result in data["results"]:
            for field in ("id", "title", "slug", "excerpt", "url"):
                self.assertIn(field, result)
