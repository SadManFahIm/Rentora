"""Celery tasks for the image variant pipeline (Phase 16)."""

from __future__ import annotations

from celery import shared_task


@shared_task(
    name="images.generate_variants",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    soft_time_limit=120,
    time_limit=180,
)
def generate_variants_task(entity_type: str, entity_id: int, source_name: str) -> str | None:
    """Generate WebP variants for one source image (idempotent).

    Returns the count of variants written, or None when the source can't be
    read (the caller's original still works — this is a best-effort
    optimization).
    """
    from django.core.files.storage import default_storage

    from .services import generate_variants

    try:
        with default_storage.open(source_name, "rb") as handle:
            data = handle.read()
    except Exception:
        return None
    result = generate_variants(entity_type, entity_id, data)
    return str(len(result)) if result else None
