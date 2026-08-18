"""Tests for the hosted embeddings provider (Tier 4).

The provider is a thin HTTPS client; tests patch ``requests.post`` and assert
the contract: parse HF-style responses, L2-normalize, and degrade to None
(→ lite fallback) on any failure — search must never break.
"""

from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from .embedding_service import HostedEmbeddingProvider


class _FakeResponse:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("HTTP 500")

    def json(self):
        return self._payload


class HostedEmbeddingProviderTests(SimpleTestCase):
    def test_parses_hf_list_response_and_normalizes(self):
        provider = HostedEmbeddingProvider(url="https://embed.example.com", token="secret-token")
        fake = np.array([[3.0, 4.0], [0.0, 5.0]], dtype=np.float32)
        seen = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            seen["headers"] = headers
            return _FakeResponse(fake.tolist())

        with mock.patch("requests.post", side_effect=fake_post):
            out = provider.encode(["a room", "another room"])

        self.assertEqual(seen["headers"].get("Authorization"), "Bearer secret-token")
        self.assertIsNotNone(out)
        self.assertEqual(out.shape, (2, 2))
        norms = np.linalg.norm(out, axis=1)
        self.assertTrue(np.allclose(norms, 1.0, atol=1e-6))

    def test_returns_none_on_network_failure(self):
        provider = HostedEmbeddingProvider(url="https://embed.example.com")

        def boom(*a, **k):
            raise ConnectionError("down")

        with mock.patch("requests.post", side_effect=boom), self.assertLogs(level="WARNING"):
            out = provider.encode(["a room"])
        self.assertIsNone(out)

    def test_returns_none_without_url(self):
        provider = HostedEmbeddingProvider(url="")
        with self.assertLogs(level="WARNING"):
            out = provider.encode(["a room"])
        self.assertIsNone(out)

    def test_rejects_wrong_shape(self):
        provider = HostedEmbeddingProvider(url="https://embed.example.com")
        with (
            mock.patch("requests.post", return_value=_FakeResponse([[0.1, 0.2, 0.3]])),
            self.assertLogs(level="WARNING"),
        ):
            out = provider.encode(["a", "b"])
        self.assertIsNone(out)
