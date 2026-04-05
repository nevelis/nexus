"""Tests for the search app: embedding generation and search view."""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from django.test import TestCase, Client

from documents.models import Document


# ── Embedding module ─────────────────────────────────────────────────────────


class TestGenerateEmbedding(TestCase):
    """Tests for search.embeddings.generate_embedding.

    These tests patch _get_model directly so we never load the real
    SentenceTransformer model (slow, large) during the test run.
    """

    def _make_mock_model(self, dims=384):
        mock = MagicMock()
        mock.encode.return_value = np.ones(dims, dtype=np.float32)
        return mock

    def test_returns_list_of_floats(self):
        import search.embeddings as emb
        mock_model = self._make_mock_model()
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = emb.generate_embedding("hello world")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(v, float) for v in result))

    def test_returns_correct_dimensions(self):
        import search.embeddings as emb
        mock_model = self._make_mock_model(dims=384)
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = emb.generate_embedding("some text")
        self.assertEqual(len(result), 384)

    def test_passes_text_to_encode(self):
        import search.embeddings as emb
        mock_model = self._make_mock_model()
        with patch.object(emb, "_get_model", return_value=mock_model):
            emb.generate_embedding("my document text")
        mock_model.encode.assert_called_once_with("my document text")

    def test_returns_none_on_model_error(self):
        import search.embeddings as emb
        with patch.object(emb, "_get_model", side_effect=RuntimeError("model load failed")):
            result = emb.generate_embedding("test")
        self.assertIsNone(result)

    def test_returns_none_on_encode_error(self):
        import search.embeddings as emb
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("encode failed")
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = emb.generate_embedding("test")
        self.assertIsNone(result)

    def test_model_lazy_loaded(self):
        """_get_model is not called until generate_embedding is first invoked."""
        import search.embeddings as emb
        mock_model = self._make_mock_model()
        with patch("search.embeddings.SentenceTransformer", return_value=mock_model) as mock_cls:
            # Reset the cached model so we can observe the lazy load
            original_model = emb._model
            emb._model = None
            try:
                emb.generate_embedding("trigger load")
                mock_cls.assert_called_once_with(emb._MODEL_NAME)
            finally:
                emb._model = original_model


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
