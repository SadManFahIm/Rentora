"""Portable pgvector field for Rentora.

PostgreSQL (production) stores real ``vector`` columns backed by the pgvector
extension and indexed with HNSW; other backends (SQLite for local dev / CI)
store the vector as a JSON array in a text column so the entire test suite
runs with zero extra services. ``EmbeddingService.search_similar`` branches on
``connection.vendor`` and falls back to a Python cosine scan when pgvector is
not available.

The dimension is fixed per table (pgvector requires ``vector(n)``); see
``settings.EMBEDDING_DIMENSIONS``.
"""

from __future__ import annotations

import json

from django.db import connection, models


class VectorField(models.Field):
    """A fixed-dimension embedding vector (pgvector on PostgreSQL, JSON text
    elsewhere). Values are stored/returned as lists of floats."""

    description = "Embedding vector (pgvector on PostgreSQL, JSON text fallback)"

    def __init__(self, dimensions: int | None = None, *args, **kwargs):
        self.dimensions = dimensions
        kwargs.setdefault("editable", False)
        super().__init__(*args, **kwargs)

    def db_type(self, connection) -> str:
        if connection.vendor == "postgresql":
            return "vector" if self.dimensions is None else f"vector({self.dimensions})"
        return "text"

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(v) for v in value]
        return self._parse(value)

    def to_python(self, value):
        if value is None or isinstance(value, (list, tuple)):
            return value
        return self._parse(value)

    def _parse(self, raw: str) -> list[float]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        stripped = (raw or "").strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            return [float(v) for v in json.loads(stripped)]
        # pgvector returns the bare form `[0.1, 0.2]` via psycopg2; tolerate
        # whitespace variants and brace form just in case.
        cleaned = stripped.replace("{", "[").replace("}", "]")
        return [float(v) for v in json.loads(cleaned)]

    def get_prep_value(self, value):
        if value is None:
            return None
        return json.dumps([float(v) for v in value])

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return self.get_prep_value(value)


def is_pgvector_available() -> bool:
    """True when the current database is PostgreSQL (pgvector enabled)."""
    return connection.vendor == "postgresql"
