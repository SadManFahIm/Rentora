"""Tests for the embedding store, pipeline and vector search (Phase 16)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from rooms.models import Room

from .models import Embedding
from .services import (
    content_hash,
    normalize_vector,
    rooms_service,
    search_similar_rooms,
)
from .tasks import backfill_rooms, index_room, remove_room

User = get_user_model()


def make_room(owner, **kwargs):
    defaults = dict(
        title="Bright furnished room",
        description="A furnished room near the metro station with wifi and AC.",
        room_type="single",
        price=12000,
        area="Uttara",
        address="Sector 7, Uttara",
        lat=23.8759,
        lng=90.3795,
        amenities=["wifi", "ac"],
        size_sqft=250,
    )
    defaults.update(kwargs)
    return Room.objects.create(owner=owner, **defaults)


@override_settings(EMBEDDING_PROVIDER="lite")
class EmbeddingServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="emb_owner", email="emb_owner@example.com", password="test12345"
        )

    def test_normalize_vector_pads_and_unit_lengths(self):
        vec = normalize_vector([3.0, 4.0], 384)
        self.assertEqual(len(vec), 384)
        norm = sum(v * v for v in vec) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_content_hash_is_deterministic(self):
        self.assertEqual(content_hash("abc"), content_hash("abc"))
        self.assertNotEqual(content_hash("abc"), content_hash("abd"))

    def test_store_and_roundtrip(self):
        service = rooms_service()
        vec = normalize_vector([1.0, 0.0, 0.0], 384)
        row = service.store_embedding(1, vec, content_hash_value="h1")
        self.assertEqual(row.entity_id, 1)
        self.assertEqual(row.model, service.model)
        self.assertEqual(len(row.vector), 384)
        self.assertEqual(service.get_for_entity(1), row)

    def test_sync_dedupes_on_content_hash(self):
        room = make_room(self.owner)
        service = rooms_service()
        first = service.sync_for_entity(room.id, f"{room.title} {room.description}")
        self.assertIsNotNone(first)
        updated_at = first.updated_at
        again = service.sync_for_entity(room.id, f"{room.title} {room.description}")
        self.assertEqual(again, first)
        self.assertEqual(again.updated_at, updated_at)
        # Content change regenerates.
        changed = service.sync_for_entity(room.id, f"{room.title} totally different text")
        self.assertNotEqual(changed.updated_at, updated_at)

    def test_search_similar_orders_by_cosine(self):
        rooms = [
            make_room(
                self.owner, title="Budget hostel room near university", description="cheap room"
            ),
            make_room(
                self.owner, title="Luxury studio in Gulshan", description="high end apartment"
            ),
            make_room(self.owner, title="Metro station shared room", description="near station"),
        ]
        service = rooms_service()
        for room in rooms:
            service.sync_for_entity(room.id, f"{room.title} {room.description}")
        results = service.search_similar("cheap university student room", top_k=3)
        self.assertTrue(results)
        # The budget/hostel room should rank first for that query.
        self.assertEqual(results[0][0], rooms[0].id)

    def test_search_similar_respects_candidate_ids(self):
        rooms = [make_room(self.owner, title=f"Room number {i}") for i in range(3)]
        service = rooms_service()
        for room in rooms:
            service.sync_for_entity(room.id, room.title)
        results = service.search_similar("Room number", top_k=5, candidate_ids=[rooms[2].id])
        self.assertEqual([r[0] for r in results], [rooms[2].id])

    def test_delete_for_entity_removes_rows(self):
        room = make_room(self.owner)
        rooms_service().sync_for_entity(room.id, room.title)
        self.assertEqual(Embedding.objects.filter(entity_type="room", entity_id=room.id).count(), 1)
        rooms_service().delete_for_entity(room.id)
        self.assertEqual(Embedding.objects.filter(entity_type="room", entity_id=room.id).count(), 0)

    def test_search_similar_rooms_only_returns_public(self):
        public = make_room(self.owner, title="Public furnished room", is_available=True)
        private = make_room(self.owner, title="Hidden unavailable room", is_available=False)
        service = rooms_service()
        for room in (public, private):
            service.sync_for_entity(room.id, f"{room.title} {room.description}")
        results = search_similar_rooms("furnished room", top_k=5)
        result_ids = {rid for rid, _score in results}
        self.assertIn(public.id, result_ids)
        self.assertNotIn(private.id, result_ids)

    def test_no_embeddings_returns_empty(self):
        self.assertEqual(search_similar_rooms("anything", top_k=5), [])


class EmbeddingTaskTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="emb_task_owner", email="emb_task_owner@example.com", password="test12345"
        )

    @override_settings(EMBEDDING_PROVIDER="lite")
    def test_index_room_task_is_idempotent(self):
        room = make_room(self.owner)
        self.assertEqual(index_room.run(room.id), "indexed")
        self.assertEqual(index_room.run(room.id), "skipped: unchanged-or-unavailable")
        self.assertEqual(Embedding.objects.filter(entity_id=room.id).count(), 1)

    @override_settings(EMBEDDING_PROVIDER="lite")
    def test_index_room_skips_missing(self):
        self.assertEqual(index_room.run(999999), "skipped: missing")

    @override_settings(EMBEDDING_PROVIDER="lite")
    def test_remove_room_task(self):
        room = make_room(self.owner)
        index_room.run(room.id)
        self.assertEqual(Embedding.objects.filter(entity_id=room.id).count(), 1)
        room_id = room.id  # Model.delete() nulls instance.pk; capture first.
        room.delete()
        self.assertEqual(remove_room.run(room_id), "removed:1")

    @override_settings(EMBEDDING_PROVIDER="lite")
    def test_backfill_batches(self):
        rooms = [make_room(self.owner, title=f"Backfill room {i}") for i in range(3)]
        result = backfill_rooms.run(offset=0, limit=3)
        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["indexed"], 3)
        self.assertTrue(result["done"])
        self.assertEqual(Embedding.objects.filter(entity_id__in=[r.id for r in rooms]).count(), 3)
        # Idempotent re-run: all skipped.
        result2 = backfill_rooms.run(offset=0, limit=3)
        self.assertEqual(result2["indexed"], 0)


@override_settings(EMBEDDING_PROVIDER="lite")
class EmbeddingApiTests(APITestCase):
    """End-to-end: vector seam in smart search + the /similar/ endpoint."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="emb_api_owner", email="emb_api_owner@example.com", password="test12345"
        )
        self.searcher = User.objects.create_user(
            username="emb_searcher", email="emb_searcher@example.com", password="test12345"
        )
        self.room_a = make_room(
            self.owner,
            title="Budget hostel room near university",
            description="cheap room for students",
            is_available=True,
        )
        self.room_b = make_room(
            self.owner,
            title="Luxury studio in Gulshan",
            description="high end apartment",
            is_available=True,
        )
        self.room_c = make_room(
            self.owner,
            title="Hidden unavailable room",
            description="not on the market",
            is_available=False,
        )
        service = rooms_service()
        for room in (self.room_a, self.room_b, self.room_c):
            service.sync_for_entity(room.id, f"{room.title} {room.description}")

    @override_settings(VECTOR_SEARCH_ENABLED=True)
    def test_smart_search_uses_vector_rank_seam(self):
        resp = self.client.get(
            "/api/v1/rooms/?q=student room&smart=1&debug_rank=1",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Vector seam annotated the response (SQLite falls back to the Python
        # cosine scan, but the pgvector path is exercised in production).
        self.assertEqual(resp.data["rank_meta"]["rank"], "pgvector")
        ids = [r["id"] for r in resp.data["results"]]
        self.assertEqual(ids[0], self.room_a.id)

    @override_settings(VECTOR_SEARCH_ENABLED=True)
    def test_similar_endpoint_excludes_self_and_hidden(self):
        resp = self.client.get(f"/api/v1/rooms/{self.room_b.id}/similar/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in resp.data]
        self.assertNotIn(self.room_b.id, ids)
        self.assertNotIn(self.room_c.id, ids)
        self.assertIn("similarity", resp.data[0])

    @override_settings(VECTOR_SEARCH_ENABLED=False)
    def test_vector_seam_disabled_falls_back_to_keyword(self):
        resp = self.client.get("/api/v1/rooms/?q=student room&smart=1&debug_rank=1", format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp.data["rank_meta"].get("rank"), "pgvector")
