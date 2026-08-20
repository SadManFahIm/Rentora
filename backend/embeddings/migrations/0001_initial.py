"""Initial embedding store (Phase 16 — pgvector).

PostgreSQL: creates the ``vector`` extension, the ``embeddings_embedding``
table with a ``vector(384)`` column and an HNSW cosine-distance index.

SQLite/other dev backends: the table is created with a JSON-text vector column
and no index; ``EmbeddingService.search_similar`` uses a Python cosine scan
instead, so local dev and CI run with zero extra services.

The ``vector(n)`` dimension matches ``settings.EMBEDDING_DIMENSIONS`` (default
384). Changing it requires a new ``ALTER COLUMN ... TYPE vector(m)`` migration.
"""

from __future__ import annotations

from django.db import migrations, models

import embeddings.fields


class RunSQLPostgres(migrations.RunSQL):
    """RunSQL that only executes on PostgreSQL (skipped on dev backends)."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        RunSQLPostgres(
            sql="CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector",
        ),
        migrations.CreateModel(
            name="Embedding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(db_index=True, max_length=64),
                ),
                ("entity_id", models.PositiveBigIntegerField()),
                ("model", models.CharField(max_length=64)),
                ("dimensions", models.PositiveIntegerField(default=0)),
                (
                    "vector",
                    embeddings.fields.VectorField(
                        blank=True, dimensions=384, editable=False, null=True
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["entity_type", "entity_id", "model"],
                        name="embedding_entity_unique",
                    )
                ],
                "indexes": [
                    models.Index(fields=["entity_type", "model"], name="embedding_type_model_idx"),
                    models.Index(
                        fields=["entity_type", "content_hash"], name="embedding_type_hash_idx"
                    ),
                ],
            },
        ),
        RunSQLPostgres(
            sql=(
                "CREATE INDEX IF NOT EXISTS embedding_vector_hnsw_idx "
                "ON embeddings_embedding USING hnsw (vector vector_cosine_ops)"
            ),
            reverse_sql=("DROP INDEX IF EXISTS embedding_vector_hnsw_idx"),
        ),
    ]
