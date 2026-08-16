"""Tier-3 embedding tests — provider mode selection + disk-persisted matrix.

The neural matrix is expensive to build, so it must (a) be persisted to
disk keyed by provider + data fingerprint, (b) be reused by every worker
without re-encoding the corpus, and (c) never break search when the heavy
dependency is missing.
"""

import shutil
import tempfile

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from rooms.embedding_service import (
    EmbeddingIndex,
    LiteEmbeddingProvider,
    get_provider,
)
from rooms.models import Room

User = get_user_model()


def make_room(owner, title="Embed Test Room"):
    return Room.objects.create(
        owner=owner,
        title=title,
        description="A room with wifi and a balcony near the university.",
        room_type="single",
        price=9000,
        area="Uttara",
        address="Sector 4, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi"],
        size_sqft=200,
    )


class FakeProvider:
    """Counts encode() calls so tests can prove cache hits skip recompute."""

    name = "fake-test"

    def __init__(self):
        self.encodes = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.encodes += 1
        matrix = np.zeros((len(texts), 4), dtype=np.float32)
        for i, text in enumerate(texts):
            matrix[i] = np.asarray([1.0, float(i), len(text) % 7, 0.5], dtype=np.float32)
        return matrix


class ProviderModeTests(TestCase):
    @override_settings(SEMANTIC_EMBEDDING_MODE="lite", SEMANTIC_SEARCH_ENABLED=True)
    def test_lite_mode_forces_lite_provider(self):
        provider = get_provider()
        self.assertIsInstance(provider, LiteEmbeddingProvider)

    @override_settings(SEMANTIC_EMBEDDING_MODE="neural", SEMANTIC_SEARCH_ENABLED=True)
    def test_neural_mode_falls_back_gracefully_without_package(self):
        # sentence-transformers is not installed in CI — must degrade to lite,
        # never return None (search must not break).
        provider = get_provider()
        self.assertIsNotNone(provider)
        self.assertIsInstance(provider, LiteEmbeddingProvider)

    @override_settings(SEMANTIC_SEARCH_ENABLED=False)
    def test_disabled_returns_none(self):
        self.assertIsNone(get_provider())


class DiskCacheTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="emb-cache-")
        self.owner = User.objects.create_user(
            username="emb_owner", email="emb_owner@example.com", password="test12345"
        )
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _index(self, provider):
        return EmbeddingIndex(provider)

    def test_build_persists_and_cache_hit_skips_recompute(self):
        make_room(self.owner)
        with override_settings(SEMANTIC_EMBEDDING_CACHE_DIR=self.tmp, SEMANTIC_SEARCH_ENABLED=True):
            provider = FakeProvider()
            index = self._index(provider)
            self.assertTrue(index.build())
            self.assertEqual(provider.encodes, 1)
            self.assertTrue(index._cache_path().exists())

            # A fresh index (same provider, same data) must load from disk
            # without re-encoding the corpus.
            provider2 = FakeProvider()
            index2 = self._index(provider2)
            self.assertTrue(index2.build())
            self.assertEqual(provider2.encodes, 0)
            self.assertEqual(index2.room_ids, index.room_ids)
            np.testing.assert_allclose(index2.matrix, index.matrix)

    def test_stale_cache_recomputes(self):
        room = make_room(self.owner)
        with override_settings(SEMANTIC_EMBEDDING_CACHE_DIR=self.tmp, SEMANTIC_SEARCH_ENABLED=True):
            provider = FakeProvider()
            index = self._index(provider)
            self.assertTrue(index.build())
            self.assertEqual(provider.encodes, 1)

            # Changing room data invalidates the fingerprint -> recompute.
            room.title = "Updated title"
            room.save()
            provider2 = FakeProvider()
            index2 = self._index(provider2)
            self.assertTrue(index2.build())
            self.assertEqual(provider2.encodes, 1)

    def test_empty_corpus_no_cache_file(self):
        with override_settings(SEMANTIC_EMBEDDING_CACHE_DIR=self.tmp, SEMANTIC_SEARCH_ENABLED=True):
            provider = FakeProvider()
            index = self._index(provider)
            self.assertFalse(index.build())
            self.assertFalse(index._cache_path().exists())
