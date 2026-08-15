"""Tier-1 quick win — same-query semantic search cache.

Verifies that repeated identical smart-search / Copilot queries over the
same pool reuse the cached ranking (no recomputation), while pool changes,
authenticated (personalized) users, debug-metadata requests and the
disabled flag all bypass the cache.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from rooms.semantic_cache import cached_hybrid_rank

User = get_user_model()

RANK_RESULT = {"ids": [3, 1, 2], "metadata": {}}


class SemanticCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def _rank(self, *args, **kwargs):
        return RANK_RESULT

    def test_identical_query_and_pool_is_cached(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            first = cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            second = cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
        self.assertEqual(first["ids"], RANK_RESULT["ids"])
        self.assertEqual(second["ids"], RANK_RESULT["ids"])
        rank.assert_called_once()  # second call served from cache

    def test_pool_membership_change_invalidates(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            cached_hybrid_rank("Uttara room", [1, 2, 3, 4], top_k=10)
        self.assertEqual(rank.call_count, 2)  # different pool -> recompute

    def test_query_change_invalidates(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            cached_hybrid_rank("Mirpur flat", [1, 2, 3], top_k=10)
        self.assertEqual(rank.call_count, 2)

    def test_top_k_is_part_of_the_key(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=60)
        self.assertEqual(rank.call_count, 2)

    def test_authenticated_user_bypasses_cache(self):
        user = User.objects.create_user(
            username="cache_user", email="cache@example.com", password="x"
        )
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], user=user, top_k=10)
            cached_hybrid_rank("Uttara room", [1, 2, 3], user=user, top_k=10)
        self.assertEqual(rank.call_count, 2)  # personalized -> never cached

    def test_debug_metadata_bypasses_cache(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], include_metadata=True, top_k=10)
            cached_hybrid_rank("Uttara room", [1, 2, 3], include_metadata=True, top_k=10)
        self.assertEqual(rank.call_count, 2)

    @override_settings(SEMANTIC_SEARCH_CACHE_ENABLED=False)
    def test_disabled_flag_bypasses_cache(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
        self.assertEqual(rank.call_count, 2)

    def test_none_result_is_never_cached(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", return_value=None) as rank:
            first = cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
            second = cached_hybrid_rank("Uttara room", [1, 2, 3], top_k=10)
        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(rank.call_count, 2)  # nothing cached on None

    def test_empty_pool_skips_cache(self):
        with mock.patch("rooms.semantic_cache.hybrid_rank", side_effect=self._rank) as rank:
            cached_hybrid_rank("Uttara room", [], top_k=10)
        self.assertEqual(rank.call_count, 1)
