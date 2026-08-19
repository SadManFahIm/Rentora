"""Celery tasks for the fraud app — per-room auto-scan + scheduled catalogue re-scan."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def scan_room(room_id: int):
    """Run the detector on one room (auto-scan on creation) and alert the owner.

    Dispatched by ``fraud.signals.scan_room_on_create``. In eager mode (no
    broker, the local default) it executes synchronously — identical
    behaviour to the old inline signal call.
    """
    from rooms.models import Room

    from .services.detectors import run_scan
    from .signals import notify_fraud_flag

    room = Room.objects.filter(pk=room_id).first()
    if room is None:
        logger.warning("Fraud scan skipped: room %s no longer exists.", room_id)
        return {"room_id": room_id, "skipped": True}

    report = run_scan(room)
    notify_fraud_flag(room, report)
    return {"room_id": room_id, "severity": report.severity, "score": report.score}


@shared_task
def scan_all_rooms():
    """Re-run the fraud detector over the whole catalogue (daily beat)."""
    from .services.catalogue import scan_all_rooms as _scan_all_rooms

    return _scan_all_rooms()


@shared_task
def detect_rings():
    """Recompute fraud rings and re-scan affected rooms (weekly beat).

    Ring membership is derived from live data (phones, audit IPs, areas), so
    the weekly run mainly keeps the persisted ``fraud_ring`` signals fresh —
    every room owned by a ring member is re-scanned so its report reflects the
    current ring state.
    """
    from rooms.models import Room

    from .services.detectors import run_scan
    from .services.rings import detect_rings as _detect_rings

    result = _detect_rings()
    affected_user_ids = {
        member["user_id"] for ring in result["rings"] for member in ring["members"]
    }
    re_scanned = 0
    for room in Room.objects.filter(owner_id__in=affected_user_ids).iterator(chunk_size=100):
        run_scan(room)
        re_scanned += 1
    return {
        "ring_count": result["ring_count"],
        "user_count": result["user_count"],
        "re_scanned": re_scanned,
    }
