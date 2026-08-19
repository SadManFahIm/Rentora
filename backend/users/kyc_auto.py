"""Automated KYC pre-screening (Tier 2).

A deterministic, explainable first pass over a tenant's identity document
that *recommends* a decision to the admin queue — it never decides alone.

What it checks (each check produces a human-readable reason, so the
recommendation is auditable):

1. **Document parses** — the uploaded file is a real image (Pillow can open
   it) or a real PDF (``%PDF`` magic), not a renamed blob.
2. **Not reused** — the document's perceptual hash is compared against other
   users' recently-submitted verification documents (and landlord KYC docs).
   The same scan submitted from two accounts is the classic fraud tell.
3. **Readable size** — an identity scan below ~400px is usually a screenshot
   or a crop; flagged for review.
4. **Complete profile** — phone / date-of-birth / name present supports the
   identity claim (weak signal).
5. **Attempt history** — repeated prior rejections/expiries are a signal the
   submitter keeps failing (or keeps trying to game) the check.

Scoring: 100 - penalties, floored at 0. ``recommend_approve`` requires a
solid score (>= 70) AND a parseable, non-duplicate document. Everything else
is ``recommend_review`` — the human decision stays the source of truth and
the recommendation is only queue-sorting.
"""

from __future__ import annotations

import os
from datetime import timedelta

from django.utils import timezone

# Penalties (of 100). Kept as module constants so tests can reason about them.
PENALTY_INVALID_DOC = 45
PENALTY_DUPLICATE = 40
PENALTY_TINY = 15
PENALTY_INCOMPLETE_PROFILE = 10
PENALTY_REPEAT_ATTEMPTS = 10

APPROVE_SCORE = 70
MIN_DOC_DIMENSION = 400
DUPLICATE_HAMMING = 8  # bits of 64-hash tolerance (same as image-search)
DUPLICATE_LOOKBACK_DAYS = 90
DUPLICATE_MAX_SCAN = 200
REPEAT_ATTEMPTS_MIN = 2


def _is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def _image_size(path: str) -> tuple[int, int] | None:
    """(width, height) of an image file, or None when it doesn't parse."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def _phash(path: str) -> str | None:
    """64-bit average hash of an image file, or None (non-image/unreadable)."""
    try:
        from PIL import Image

        from rooms.image_search import average_hash

        with Image.open(path) as img:
            return average_hash(img)
    except Exception:
        return None


def _find_duplicate(
    path: str, exclude_verification_id: int | None = None
) -> tuple[str, str] | None:
    """Compare ``path`` against other accounts' recent KYC/tenant documents.

    Returns ``(username, kind)`` of the first visually matching document, or
    None. The current submission itself is excluded (its own prior copies are
    the attempt-history signal, not a cross-account fraud tell). Bounded
    (lookback window + max scans) so a pre-screen never turns into a
    full-table scan.
    """
    from rooms.image_search import hamming_distance

    from .models import KycDocument, TenantVerification

    hash_a = _phash(path)
    if hash_a is None:
        return None

    since = timezone.now() - timedelta(days=DUPLICATE_LOOKBACK_DAYS)
    candidates = []
    verifications = TenantVerification.objects.filter(created_at__gte=since).select_related("user")
    if exclude_verification_id is not None:
        verifications = verifications.exclude(pk=exclude_verification_id)
    for verification in verifications.order_by("-created_at")[:DUPLICATE_MAX_SCAN]:
        if verification.file:
            candidates.append((verification.user.username, "tenant", verification.file.path))
    for document in (
        KycDocument.objects.filter(created_at__gte=since)
        .select_related("user")
        .order_by("-created_at")[:DUPLICATE_MAX_SCAN]
    ):
        if document.file:
            candidates.append((document.user.username, "landlord", document.file.path))

    for username, kind, candidate_path in candidates:
        try:
            if not os.path.exists(candidate_path):
                continue
            hash_b = _phash(candidate_path)
            if hash_b is not None and hamming_distance(hash_a, hash_b) <= DUPLICATE_HAMMING:
                return username, kind
        except Exception:
            continue
    return None


def _failed_attempt_count(user) -> int:
    """Prior decisions that ended in rejection/needs-review.

    Read from the append-only audit log (actions ``tenant_kyc.rejected`` /
    ``tenant_kyc.needs_review``), not from ``TenantVerification`` — that
    record is one-per-user, so it can't hold history; the audit trail can.
    """
    from audit.models import AuditLogEntry

    return AuditLogEntry.objects.filter(
        actor__isnull=False,
        action__in=["tenant_kyc.rejected", "tenant_kyc.needs_review"],
        target_id=str(user.pk),
    ).count()


def auto_screen(verification) -> dict:
    """Score one verification submission. Never raises for a bad file —
    that's exactly what it's designed to catch."""
    path = verification.file.path if verification.file else ""
    reasons: list[str] = []
    score = 100
    doc_ok = False
    # Hard defects (unreadable, reused, too small) force review regardless of
    # the remaining score — an admin always looks at those.
    needs_review = False

    # 1. Document parses.
    if not path or not os.path.exists(path):
        reasons.append("document file missing on disk")
        score -= PENALTY_INVALID_DOC
        needs_review = True
    elif _is_pdf(path):
        doc_ok = True
    else:
        size = _image_size(path)
        if size is None:
            reasons.append("document is not a readable image or PDF")
            score -= PENALTY_INVALID_DOC
            needs_review = True
        else:
            doc_ok = True
            # 3. Readable size.
            if min(size) < MIN_DOC_DIMENSION:
                reasons.append(
                    f"document is only {size[0]}x{size[1]}px - likely a screenshot or crop"
                )
                score -= PENALTY_TINY
                needs_review = True

    # 2. Not reused across accounts.
    if doc_ok and not _is_pdf(path):
        duplicate = _find_duplicate(path, exclude_verification_id=verification.pk)
        if duplicate is not None:
            reasons.append(
                f"document visually matches another account's submission ({duplicate[0]})"
            )
            score -= PENALTY_DUPLICATE
            needs_review = True

    # 4. Profile completeness (weak supporting signal).
    user = verification.user
    if not (user.phone and user.date_of_birth and (user.first_name or user.last_name)):
        reasons.append("profile is missing phone/date-of-birth/name")
        score -= PENALTY_INCOMPLETE_PROFILE

    # 5. Attempt history.
    failed = _failed_attempt_count(user)
    if failed >= REPEAT_ATTEMPTS_MIN:
        reasons.append(f"{failed} prior unsuccessful verification attempts")
        score -= PENALTY_REPEAT_ATTEMPTS

    # 6. OCR auto-extraction (Phase 15, C4): when an OCR provider is
    # configured, a structurally valid NID number extracted from the document
    # earns a small, explainable boost. Structural only — it never claims the
    # document belongs to this user, and an admin always decides.
    ocr: dict | None = None
    if doc_ok and not _is_pdf(path):
        from .kyc_ocr import ocr_score_boost, ocr_screen

        screen = ocr_screen(verification)
        if screen["extracted"] is not None:
            ocr = screen["extracted"]
            score += ocr_score_boost(ocr)
            reasons.append(
                f"OCR extracted a structurally valid NID number (confidence: {ocr['confidence']})"
            )

    score = max(0, min(100, score))
    if score >= APPROVE_SCORE and doc_ok and not needs_review:
        result = "recommend_approve"
    else:
        result = "recommend_review"

    return {
        "score": score,
        "result": result,
        "reasons": reasons,
        "ocr": ocr,
    }
