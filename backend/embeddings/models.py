"""Embedding storage (Phase 16 — pgvector).

One row per (entity_type, entity_id, model). Vectors are stored via the
portable :class:`~embeddings.fields.VectorField` — real ``vector`` columns on
PostgreSQL, JSON text elsewhere — so the whole suite runs on SQLite while
production gets native pgvector indexing (HNSW, cosine distance).

A deterministic ``content_hash`` of the source text prevents duplicate
generation: when the source content is unchanged the row is reused instead of
re-embedded, which keeps Celery re-runs cheap and idempotent.
"""

from __future__ import annotations

from django.db import models

from .fields import VectorField


class Embedding(models.Model):
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.PositiveBigIntegerField()
    model = models.CharField(max_length=64)
    dimensions = models.PositiveIntegerField(default=0)
    vector = VectorField(dimensions=384, null=True, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "entity_id", "model"],
                name="embedding_entity_unique",
            )
        ]
        indexes = [
            models.Index(fields=["entity_type", "model"], name="embedding_type_model_idx"),
            models.Index(fields=["entity_type", "content_hash"], name="embedding_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_id} ({self.model})"
