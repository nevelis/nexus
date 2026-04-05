"""Tests for the search app: embedding generation and search view."""

from unittest.mock import MagicMock, patch

import numpy as np
from django.test import Client, TestCase

import search.embeddings as emb
from documents.models import Document

# Capture the real generate_embedding function *at module import time*, before
# the conftest autouse fixture replaces the module attribute with a no-op lambda.
# This lets TestGenerateEmbedding call the real implementation while still
# benefiting from _get_model being patched (no actual ML model loaded).
_real_generate_embedding = emb.generate_embedding

# ── Embedding module ─────────────────────────────────────────────────────────


class TestGenerateEmbedding(TestCase):
    """Tests for search.embeddings.generate_embedding.

    These tests patch _get_model directly so we never load the real
    SentenceTransformer model (slow, large) during the test run.

    We call _real_generate_embedding (captured before conftest monkeypatching)
    rather than emb.generate_embedding because the conftest autouse fixture
    replaces the module attribute with a None-returning stub for all other tests.
    """

    def _make_mock_model(self, dims=384):
        mock = MagicMock()
        mock.encode.return_value = np.ones(dims, dtype=np.float32)
        return mock

    def test_returns_list_of_floats(self):
        mock_model = self._make_mock_model()
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = _real_generate_embedding("hello world")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(v, float) for v in result))

    def test_returns_correct_dimensions(self):
        mock_model = self._make_mock_model(dims=384)
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = _real_generate_embedding("some text")
        self.assertEqual(len(result), 384)

    def test_passes_text_to_encode(self):
        mock_model = self._make_mock_model()
        with patch.object(emb, "_get_model", return_value=mock_model):
            _real_generate_embedding("my document text")
        mock_model.encode.assert_called_once_with("my document text")

    def test_returns_none_on_model_error(self):
        with patch.object(emb, "_get_model", side_effect=RuntimeError("model load failed")):
            result = _real_generate_embedding("test")
        self.assertIsNone(result)

    def test_returns_none_on_encode_error(self):
        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("encode failed")
        with patch.object(emb, "_get_model", return_value=mock_model):
            result = _real_generate_embedding("test")
        self.assertIsNone(result)

    def test_model_lazy_loaded(self):
        """_get_model is not called until generate_embedding is first invoked."""
        mock_model = self._make_mock_model()
        # SentenceTransformer is a lazy import inside _get_model — patch it at
        # the source package so the 'from sentence_transformers import ...' picks
        # up the mock.
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ) as mock_cls:
            original_model = emb._model
            emb._model = None
            try:
                _real_generate_embedding("trigger load")
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
