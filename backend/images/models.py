"""Optimized image variant storage (Phase 16 — WebP pipeline).

One row per (entity_type, entity_id, size_key). Original uploads are kept as
the archival source of truth; the pipeline additionally writes WebP variants
(thumbnail/small/medium/large) that the API exposes as ``variants`` for the
frontend's ``srcset`` — cutting bytes on the wire without re-encoding per
request. Variants are keyed by ``content_hash`` of the *source image bytes*
at generation time so a regeneration after the source changes never leaves a
stale-size row.
"""

from __future__ import annotations

from django.db import models


class ImageVariant(models.Model):
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.PositiveBigIntegerField()
    size_key = models.CharField(max_length=32)  # thumbnail|small|medium|large
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    file = models.FileField(upload_to="image_variants/%Y/%m/")
    format = models.CharField(max_length=16, default="webp")
    source_hash = models.CharField(max_length=64, db_index=True, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "entity_id", "size_key"],
                name="image_variant_entity_size_unique",
            )
        ]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"], name="image_variant_entity_idx")
        ]
        ordering = ["entity_type", "entity_id", "size_key"]

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_id}/{self.size_key}"
