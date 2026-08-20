"""Celery tasks for the embedding pipeline (Phase 16).

Indexing is fully asynchronous: room creation/update only enqueues a task and
the provider/DB work happens on the ``embeddings`` queue. Tasks are idempotent
(content-hash dedupe), retry transient failures with exponential backoff, and
never raise — a broken provider degrades to the existing keyword search.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.apps import apps

from .models import Embedding
from .services import content_hash, room_text, rooms_service

logger = logging.getLogger(__name__)


@shared_task(
    name="embeddings.index_room",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
    acks_late=True,
    ignore_result=True,
    soft_time_limit=120,
    time_limit=180,
)
def index_room(room_id: int, *, force: bool = False) -> str | None:
    """Generate + store the embedding for one room (idempotent)."""
    Room = apps.get_model("rooms", "Room")
    try:
        room = Room.objects.only("id", "title", "area", "description", "address", "amenities").get(
            pk=room_id
        )
    except Room.DoesNotExist:
        return "skipped: missing"
    service = rooms_service()
    text = room_text(room)
    digest = content_hash(text)
    if (
        not force
        and Embedding.objects.filter(
            entity_type=service.entity_type,
            entity_id=room_id,
            model=service.model,
            content_hash=digest,
        ).exists()
    ):
        return "skipped: unchanged-or-unavailable"
    embedding = service.sync_for_entity(
        room_id, text, metadata={"room_title": room.title}, force=force
    )
    return "indexed" if embedding else "skipped: unchanged-or-unavailable"


@shared_task(
    name="embeddings.remove_room",
    ignore_result=True,
    acks_late=True,
)
def remove_room(room_id: int) -> str:
    """Remove all embedding rows for a deleted room (deletion sync)."""
    deleted = rooms_service().delete_for_entity(room_id)
    return f"removed:{deleted}"


@shared_task(
    name="embeddings.backfill",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    soft_time_limit=300,
    time_limit=600,
)
def backfill_rooms(*, offset: int = 0, limit: int = 500, force: bool = False) -> dict:
    """Batch backfill of room embeddings with resume/retry support.

    Safe to call repeatedly: each batch is idempotent and the command advances
    ``offset`` in pages, so an interrupted run resumes where it stopped.
    """
    Room = apps.get_model("rooms", "Room")
    rooms = list(
        Room.objects.order_by("id").only(
            "id", "title", "area", "description", "address", "amenities"
        )[offset : offset + limit]
    )
    if not rooms:
        return {"processed": 0, "done": True}
    service = rooms_service()
    indexed = 0
    skipped = 0
    for room in rooms:
        text = room_text(room)
        if (
            not force
            and Embedding.objects.filter(
                entity_type=service.entity_type,
                entity_id=room.id,
                model=service.model,
                content_hash=content_hash(text),
            ).exists()
        ):
            skipped += 1
            continue
        embedding = service.sync_for_entity(room.id, text)
        if embedding:
            indexed += 1
        else:
            skipped += 1
    done = len(rooms) < limit or not Room.objects.filter(id__gt=rooms[-1].id).exists()
    return {
        "processed": len(rooms),
        "indexed": indexed,
        "skipped": skipped,
        "done": done,
    }
