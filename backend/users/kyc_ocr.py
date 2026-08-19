"""AI NID OCR auto-extract (Phase 15 — C4).

The KYC pre-screen gains an OCR layer: when an OCR provider is configured, the
uploaded document's text is extracted and parsed into structured NID fields
(NID number, name, date of birth). The parsed fields go into the admin-facing
``auto_screen_detail`` and give the pre-screen a small, explainable boost when
a *structurally valid* NID number is found.

Honesty contract (same as the rest of the KYC pipeline):

- ``parse_nid_text`` is pure, deterministic regex parsing — it extracts a
  number that *looks like* a Bangladeshi NID (13 or 17 digits) and nearby
  name/DOB lines. It never claims the document belongs to the submitter:
  structural validity only, never identity proof.
- OCR itself is provider-based (``KYC_OCR_PROVIDER``): ``none`` (default,
  works offline — no extraction happens) or ``http`` (posts the image to a
  gateway and parses the returned text). A gateway failure degrades to "no
  extraction", never to a wrong answer.
- The boost is capped and explainable — the admin still decides.
"""

from __future__ import annotations

import logging
import os
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Score boost applied when a structurally valid NID number is extracted.
OCR_BOOST = 5

_GATEWAY_TIMEOUT_SECONDS = 15

# Bangladesh NID numbers: 17 digits (current smart NID) or 13 digits (legacy).
_NID_17_RE = re.compile(r"\b\d{17}\b")
_NID_13_RE = re.compile(r"\b\d{13}\b")
# DD/MM/YYYY or DD-MM-YYYY (Bangladesh dates are day-first).
_DOB_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
_BANGLA_LETTERS_RE = re.compile(r"[\u0980-\u09FF]")
_EN_WORD_RE = re.compile(r"[A-Za-z]+")


def _valid_date(day: int, month: int, year: int) -> bool:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    if month in (4, 6, 9, 11) and day > 30:
        return False
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        if day > (29 if leap else 28):
            return False
    return True


def _name_candidates(text: str, number_index: int) -> list[tuple[int, str]]:
    """Lines that plausibly hold a person's name, with their line index.

    A candidate line: 2-4 words, no digits, and either every English word is
    capitalized (names on NIDs are printed in caps) or it's a Bangla line.
    """
    lines = [line.strip() for line in text.splitlines()]
    candidates: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if not line:
            continue
        if re.search(r"\d", line):
            continue
        words = line.split()
        if not (2 <= len(words) <= 4):
            continue
        if _BANGLA_LETTERS_RE.search(line):
            candidates.append((idx, line))
            continue
        en_words = _EN_WORD_RE.findall(line)
        if len(en_words) == len(words) and all(w[0].isupper() for w in en_words):
            candidates.append((idx, line))
    return candidates


def parse_nid_text(text: str) -> dict | None:
    """Extract structured fields from OCR'd NID text. Pure + deterministic.

    Returns ``{nid_number, name, date_of_birth, confidence}`` or None when no
    NID number is found. ``confidence``: ``high`` (number + name + DOB),
    ``medium`` (number + one of them), ``low`` (number only). The result is
    *structural* — it says nothing about whether the document belongs to the
    person who uploaded it.
    """
    if not text:
        return None

    match = _NID_17_RE.search(text) or _NID_13_RE.search(text)
    if match is None:
        return None
    nid_number = match.group(0)

    # Nearest name line to the number line (the number sits in the name block
    # on Bangladeshi NIDs), preferring lines after it.
    number_index = text[: match.start()].count("\n")
    candidates = sorted(
        _name_candidates(text, number_index),
        key=lambda pair: (abs(pair[0] - number_index), pair[0] > number_index),
    )
    name = candidates[0][1] if candidates else None

    dob = None
    dob_match = _DOB_RE.search(text)
    if dob_match is not None:
        day, month, year = (int(dob_match.group(i)) for i in (1, 2, 3))
        if _valid_date(day, month, year):
            dob = f"{day:02d}/{month:02d}/{year}"

    if name and dob:
        confidence = "high"
    elif name or dob:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "nid_number": nid_number,
        "name": name,
        "date_of_birth": dob,
        "confidence": confidence,
    }


def extract_ocr_text(path: str) -> str | None:
    """OCR a document image via the configured provider.

    ``KYC_OCR_PROVIDER=none`` (default): no extraction (returns None — the
    pipeline simply runs without OCR). ``http``: posts the image to
    ``KYC_OCR_GATEWAY_URL`` (Bearer ``KYC_OCR_GATEWAY_API_KEY``, multipart
    field ``file``), expecting ``{"text": "..."}``. Any deviation returns
    None — a gateway outage never breaks the KYC flow.
    """
    if not path or not os.path.exists(path):
        return None
    provider = (getattr(settings, "KYC_OCR_PROVIDER", "") or "none").strip().lower()
    if provider != "http":
        return None

    url = settings.KYC_OCR_GATEWAY_URL
    if not url:
        logger.warning("KYC_OCR_PROVIDER=http but KYC_OCR_GATEWAY_URL is empty")
        return None

    import requests

    headers = {}
    if settings.KYC_OCR_GATEWAY_API_KEY:
        headers["Authorization"] = f"Bearer {settings.KYC_OCR_GATEWAY_API_KEY}"
    try:
        with open(path, "rb") as fh:
            response = requests.post(
                url,
                files={"file": fh},
                headers=headers,
                timeout=_GATEWAY_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("KYC OCR gateway failed (no extraction): %s", exc)
        return None

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return text[:4000]


def ocr_screen(verification) -> dict:
    """Run the OCR layer for one verification submission.

    Returns ``{enabled, extracted, note}`` — ``extracted`` is the parsed NID
    fields or None. Never raises on a bad file: those are the pre-screen's
    job, and OCR is an enhancement, not a gate.
    """
    if not getattr(settings, "KYC_OCR_ENABLED", True):
        return {"enabled": False, "extracted": None, "note": "OCR disabled"}
    if not verification.file:
        return {"enabled": True, "extracted": None, "note": "no document file"}

    path = verification.file.path
    if not os.path.exists(path):
        return {"enabled": True, "extracted": None, "note": "document missing on disk"}
    if _is_pdf(path):
        return {"enabled": True, "extracted": None, "note": "OCR skipped for PDF scans"}

    text = extract_ocr_text(path)
    parsed = parse_nid_text(text) if text else None
    if parsed is None:
        return {"enabled": True, "extracted": None, "note": "no NID fields extracted"}
    return {
        "enabled": True,
        "extracted": parsed,
        "note": "NID number extracted (structural check only)",
    }


def ocr_score_boost(extracted: dict | None) -> int:
    """Small, explainable boost for a structurally valid NID number."""
    if extracted is None or not extracted.get("nid_number"):
        return 0
    return OCR_BOOST


def _is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False
