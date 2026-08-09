"""Shared catalogue-wide fraud scan (command + Celery task)."""

from __future__ import annotations

from rooms.models import Room


def scan_all_rooms() -> dict[str, int]:
    """Re-run the fraud detector over every room in the database.

    Returns ``{"scanned": n, "flagged": m}``. Used by both the ``scan_rooms``
    management command and the ``fraud.tasks.scan_all_rooms`` beat task so a
    scheduled and a manual run behave identically.
    """
    from fraud.services.detectors import run_scan

    flagged = 0
    scanned = 0
    for room in Room.objects.all().iterator(chunk_size=100):
        report = run_scan(room)
        scanned += 1
        if report.is_flagged:
            flagged += 1
    return {"scanned": scanned, "flagged": flagged}
