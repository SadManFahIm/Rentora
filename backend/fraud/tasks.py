"""Celery tasks for the fraud app — per-room auto-scan + scheduled catalogue re-scan.

Phase 17 task stubs (Stage 2): the actual implementations land in Stages 3-7.
These stubs ensure the Celery beat schedule references resolve at import time
and the task signatures are established.
"""

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


# ---------------------------------------------------------------------------
# Phase 17 — Graph & Deep Trust task stubs (Stage 2)
# ---------------------------------------------------------------------------
# These stubs ensure beat-schedule references resolve. Full implementations
# land in Stages 3-7 when the features are built.


@shared_task
def rebuild_fraud_graph():
    """Full graph rebuild from audit logs, phones, IPs, devices (weekly beat).

    Wipes the persistent graph and rebuilds it from platform data using
    phone-sharing, audit-log IP, and user->room edges.  Recomputes
    communities and risk scores at the end.
    """
    from .services.graph import rebuild_graph

    return rebuild_graph()


@shared_task
def update_graph_incremental():
    """Incremental graph update from new audit entries (every 6 hours).

    Adds only new entities and edges since the last update, then
    recomputes communities and risk scores.  Much cheaper than a
    full rebuild.
    """
    from .services.graph import update_incremental

    return update_incremental()


@shared_task
def scan_review_trust():
    """Compute trust scores for un-scored reviews (daily, 05:00).

    Scores every review that hasn't been scored yet and flags low-trust
    reviews for moderation.
    """
    from .services.review_detector import scan_review_trust_scores

    result = scan_review_trust_scores()
    logger.info(
        "scan_review_trust: scored %d reviews, flagged %d",
        result["scored"],
        result["flagged"],
    )
    return result


@shared_task
def detect_review_anomalies():
    """Detect rating distribution anomalies and review velocity spikes (daily, 05:30).

    Flags rooms with suspicious review patterns for admin review.
    """
    from .services.review_detector import detect_review_anomalies as detect

    result = detect()
    if result["count"] > 0:
        from notifications.utils import create_notification
        from users.models import User

        admins = User.objects.filter(is_staff=True)
        for admin in admins:
            create_notification(
                user=admin,
                subject=f"Review anomalies: {result['count']} issues detected",
                body=(
                    f"{result['count']} review anomalies found: "
                    + ", ".join(a["type"] for a in result["anomalies"][:5])
                ),
                category="review_anomaly",
                url="/admin/bookings/review/",
            )

    logger.info("detect_review_anomalies: found %d anomalies", result["count"])
    return result


@shared_task
def check_model_drift():
    """Compare recent predictions vs baseline; alert if threshold breached (daily).

    Runs drift checks for all active model versions: computes fraud_signal_rate,
    review_trust_avg, and photo_geo_mismatch_rate, compares against baselines,
    and creates DriftMetric records. If thresholds are breached, a RetrainRequest
    is created and admins are alerted.
    """
    from .services.model_monitor import check_all_drift

    result = check_all_drift()
    logger.info(
        "check_model_drift: %d metrics computed, %d breaches",
        result["metrics_computed"],
        result["breaches"],
    )
    return result


@shared_task
def purge_expired_liveness():
    """Clean up expired liveness challenges and old selfies (daily beat).

    Deletes challenges older than KYC_LIVENESS_RETENTION_DAYS (default 90)
    and removes their selfie files from private media storage.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from users.models import LivenessChallenge

    retention_days = getattr(settings, "KYC_LIVENESS_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)

    old_challenges = LivenessChallenge.objects.filter(created_at__lt=cutoff)
    count = old_challenges.count()

    if count == 0:
        return {"status": "ok", "deleted": 0}

    # Delete selfie files first
    for challenge in old_challenges.iterator():
        if challenge.selfie:
            try:
                challenge.selfie.delete(save=False)
            except Exception:
                logger.warning("Failed to delete selfie for challenge %s", challenge.pk)

    old_challenges.delete()
    logger.info(
        "purge_expired_liveness: deleted %d challenges older than %d days", count, retention_days
    )
    return {"status": "ok", "deleted": count}


@shared_task
def alert_graph_anomalies():
    """Alert admin when new large ring or suspicious community detected (every 6h).

    Scans the persistent graph for communities with >= 3 user nodes where
    at least one member has risk_score >= 60.  Sends in-app notification
    and email to the trust-and-safety team.

    Results are for alerting only -- they do NOT trigger automatic blocks.
    """
    from .services.graph import detect_anomalies

    anomalies = detect_anomalies()
    if not anomalies:
        return {"alerted": 0}

    from notifications.utils import create_notification
    from users.models import User

    admins = User.objects.filter(is_staff=True)
    for admin in admins:
        for anomaly in anomalies[:5]:
            create_notification(
                user=admin,
                subject=f"Graph anomaly: community {anomaly['community_id']}",
                body=(
                    f"Community {anomaly['community_id']}: "
                    f"{anomaly['member_count']} members, "
                    f"{anomaly['high_risk_count']} high-risk, "
                    f"max score {anomaly['max_risk_score']}."
                ),
                category="graph_anomaly",
                url="/admin/fraud/graphnode/",
            )

    return {"alerted": len(anomalies), "anomalies": anomalies[:5]}


@shared_task
def scan_photo_geo_mismatches():
    """Scan all rooms for photo-geo mismatches (weekly, Monday 04:00).

    Checks every room with photos against its declared lat/lng. Creates
    FraudSignal records for rooms where photos are GPS-tagged and located
    more than PHOTO_GEO_MISMATCH_THRESHOLD_KM away.
    """
    from rooms.models import Room

    from .services.photo_geo import scan_room_photo_geo

    rooms_with_gps_photos = Room.objects.filter(images__photo_lat__isnull=False).distinct()

    scanned = 0
    mismatches = 0
    for room in rooms_with_gps_photos.iterator():
        result = scan_room_photo_geo(room)
        scanned += 1
        if result["mismatch"]:
            mismatches += 1

    logger.info(
        "scan_photo_geo_mismatches: scanned %d rooms, found %d mismatches",
        scanned,
        mismatches,
    )
    return {"status": "ok", "scanned": scanned, "mismatches": mismatches}
