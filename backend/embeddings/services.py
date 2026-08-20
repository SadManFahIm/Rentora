"""Reusable embedding abstraction for Rentora (Phase 16 — pgvector).

The pipeline is deliberately provider-agnostic:

    Content
      -> Embedding Job (Celery)
      -> Embedding Provider (replaceable)
      -> PostgreSQL + pgvector (or SQLite JSON fallback)
      -> Vector Search

The provider is selected by ``EMBEDDING_PROVIDER``::

    lite     deterministic synonym-hash (zero deps, default, dev/CI parity)
    auto     sentence-transformers when installed, else lite
    neural   sentence-transformers required (falls back to lite with warning)
    hosted   hosted embeddings endpoint (HF Inference API compatible)

Every vector is normalised to ``EMBEDDING_DIMENSIONS`` so a single ``vector(n)``
column serves every provider. Duplicate generation is prevented by a
deterministic ``content_hash`` of the source text.
"""

from __future__ import annotations

import hashlib
import logging

import numpy as np
from django.conf import settings
from django.db import connection, transaction

from .models import Embedding

logger = logging.getLogger(__name__)


def content_hash(text: str) -> str:
    """Deterministic hash of the source text (dedupe key for regeneration)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def normalize_vector(values, dimensions: int) -> list[float]:
    """Pad/truncate to ``dimensions`` and L2-normalise (unit length)."""
    if values is None:
        return []
    flat = [float(v) for v in values]
    flat = flat + [0.0] * (dimensions - len(flat)) if len(flat) < dimensions else flat[:dimensions]
    norm = float(np.linalg.norm(flat)) if flat else 0.0
    if norm > 0:
        flat = [v / norm for v in flat]
    return flat


def _provider() -> object | None:
    from rooms.embedding_service import get_provider

    mode = getattr(settings, "EMBEDDING_PROVIDER", "lite").lower()
    if mode == "lite":
        from rooms.embedding_service import LiteEmbeddingProvider

        return LiteEmbeddingProvider(getattr(settings, "EMBEDDING_DIMENSIONS", 384))
    return get_provider()


def _model_name(provider) -> str:
    name = getattr(provider, "name", "unknown")
    model = getattr(provider, "model_name", name)
    return f"{name}:{model}" if model else name


class EmbeddingService:
    """Embedding generation + storage + vector search.

    All methods are safe to call from workers or requests; failures degrade to
    ``None``/``[]`` so the calling code always has a fallback.
    """

    def __init__(self, entity_type: str, model: str | None = None) -> None:
        self.entity_type = entity_type
        self._provider = None
        self._model = model

    @property
    def provider(self):
        if self._provider is None:
            self._provider = _provider()
        return self._provider

    @property
    def model(self) -> str:
        if self._model:
            return self._model
        provider = self.provider
        return _model_name(provider) if provider is not None else "unknown"

    @property
    def dimensions(self) -> int:
        return int(getattr(settings, "EMBEDDING_DIMENSIONS", 384))

    # -- generation ---------------------------------------------------------

    def generate_embedding(self, text: str) -> list[float] | None:
        """Embed a single text (None on provider failure)."""
        provider = self.provider
        if provider is None:
            return None
        try:
            matrix = provider.encode([text[:1000]])
            if matrix is None or len(matrix) == 0:
                return None
            return normalize_vector(matrix[0], self.dimensions)
        except Exception as exc:  # provider broken — caller falls back
            logger.warning("embedding generation failed (%s); provider=%s", exc, self.model)
            return None

    def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts (None on provider failure)."""
        provider = self.provider
        if provider is None or not texts:
            return None
        try:
            matrix = provider.encode([t[:1000] for t in texts])
            if matrix is None:
                return None
            return [normalize_vector(row, self.dimensions) for row in matrix]
        except Exception as exc:
            logger.warning("batch embedding generation failed (%s)", exc)
            return None

    # -- storage ------------------------------------------------------------

    def store_embedding(
        self,
        entity_id: int,
        vector: list[float],
        *,
        content_hash_value: str = "",
        metadata: dict | None = None,
    ) -> Embedding:
        """Upsert a single embedding row (deduped by content hash)."""
        norm = normalize_vector(vector, self.dimensions)
        with transaction.atomic():
            obj, _created = Embedding.objects.update_or_create(
                entity_type=self.entity_type,
                entity_id=entity_id,
                model=self.model,
                defaults={
                    "dimensions": self.dimensions,
                    "vector": norm,
                    "content_hash": content_hash_value,
                    "metadata": metadata or {},
                },
            )
        return obj

    def sync_for_entity(
        self,
        entity_id: int,
        text: str,
        *,
        metadata: dict | None = None,
        force: bool = False,
    ) -> Embedding | None:
        """Generate + store an embedding unless the content hash is unchanged.

        Returns the stored row, or None when content is unchanged (idempotent
        re-runs skip regeneration entirely) or the provider failed.
        """
        digest = content_hash(text)
        existing = Embedding.objects.filter(
            entity_type=self.entity_type,
            entity_id=entity_id,
            model=self.model,
        ).first()
        if existing is not None and not force and existing.content_hash == digest:
            return existing  # nothing changed — reuse the stored vector
        vector = self.generate_embedding(text)
        if vector is None:
            return None
        return self.store_embedding(entity_id, vector, content_hash_value=digest, metadata=metadata)

    def delete_for_entity(self, entity_id: int) -> int:
        """Remove every embedding row for an entity (deletion sync)."""
        deleted, _ = Embedding.objects.filter(
            entity_type=self.entity_type, entity_id=entity_id
        ).delete()
        return deleted

    def get_for_entity(self, entity_id: int) -> Embedding | None:
        return Embedding.objects.filter(
            entity_type=self.entity_type, entity_id=entity_id, model=self.model
        ).first()

    # -- vector search ------------------------------------------------------

    def search_similar(
        self,
        query: str,
        *,
        top_k: int = 10,
        candidate_ids: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Cosine-similarity search, best-first. Returns [(entity_id, score)].

        PostgreSQL: pushes the query down to pgvector with the HNSW index
        (``vector <=> query::vector``). Other backends: Python cosine scan over
        stored rows (fine for dev/CI). Always bounded by ``top_k``.
        """
        query_vec = self.generate_embedding(query)
        if query_vec is None or not any(query_vec):
            return []
        top_k = max(1, min(int(top_k), 200))

        if connection.vendor == "postgresql":
            return self._search_similar_pg(query_vec, top_k=top_k, candidate_ids=candidate_ids)
        return self._search_similar_python(query_vec, top_k=top_k, candidate_ids=candidate_ids)

    def _search_similar_pg(
        self, query_vec: list[float], *, top_k: int, candidate_ids: list[int] | None
    ) -> list[tuple[int, float]]:
        import json

        from django.db import connection as conn

        params: list[object] = []
        sql = f"""
            SELECT entity_id, 1 - (vector <=> %s::vector) AS score
            FROM {Embedding._meta.db_table}
            WHERE model = %s
        """
        params.extend([json.dumps(query_vec), self.model])
        if candidate_ids:
            placeholders = ", ".join(["%s"] * len(candidate_ids))
            sql += f" AND entity_id = ANY(ARRAY[{placeholders}]::bigint[])"
            params.extend(int(i) for i in candidate_ids)
        sql += " ORDER BY vector <=> %s::vector LIMIT %s"
        params.extend([json.dumps(query_vec), top_k])
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [(int(row[0]), float(row[1])) for row in cursor.fetchall()]
        except Exception as exc:
            logger.warning("pgvector search failed (%s); falling back to python scan", exc)
            return self._search_similar_python(query_vec, top_k=top_k, candidate_ids=candidate_ids)

    def _search_similar_python(
        self, query_vec: list[float], *, top_k: int, candidate_ids: list[int] | None
    ) -> list[tuple[int, float]]:
        q = np.asarray(query_vec, dtype=np.float32)
        qs = Embedding.objects.filter(entity_type=self.entity_type, model=self.model)
        if candidate_ids:
            qs = qs.filter(entity_id__in=candidate_ids)
        rows = list(qs.values_list("entity_id", "vector"))
        scored: list[tuple[int, float]] = []
        for entity_id, vec in rows:
            arr = np.asarray(vec or [], dtype=np.float32)
            if arr.size != q.size:
                arr = np.asarray(normalize_vector(list(arr), self.dimensions), dtype=np.float32)
            if arr.size:
                scored.append((entity_id, float(np.dot(q, arr))))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def has_embeddings(self, candidate_ids: list[int] | None = None) -> bool:
        qs = Embedding.objects.filter(entity_type=self.entity_type, model=self.model)
        if candidate_ids:
            qs = qs.filter(entity_id__in=candidate_ids)
        return qs.exists()


def room_text(room) -> str:
    """Searchable text blob for a Room (mirrors rooms.embedding_service)."""
    from rooms.embedding_service import _room_text

    return _room_text(room)


def rooms_service() -> EmbeddingService:
    """EmbeddingService bound to the rooms entity type."""
    return EmbeddingService(entity_type="room")


def search_similar_rooms(
    query: str, *, top_k: int = 8, exclude_ids: list[int] | None = None
) -> list[tuple[int, float]]:
    """Similar public rooms for a text query (authorisation enforced: only
    available listings are ever returned)."""
    from rooms.models import Room

    service = rooms_service()
    if not service.has_embeddings():
        return []
    public_ids = list(Room.objects.filter(is_available=True).values_list("id", flat=True))
    if exclude_ids:
        public_ids = [i for i in public_ids if i not in set(exclude_ids)]
    if not public_ids:
        return []
    results = service.search_similar(query, top_k=top_k, candidate_ids=public_ids)
    return [(rid, score) for rid, score in results if rid in set(public_ids)]
