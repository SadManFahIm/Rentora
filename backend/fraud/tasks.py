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
