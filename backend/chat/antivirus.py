"""Optional ClamAV virus scanning for chat attachments (Tier 2).

Chat uploads already pass an allow-list content-type and size check; this
adds a real malware scan on top when a ClamAV daemon is reachable. Design:

- **Opt-in** (``CLAMAV_ENABLED``): dev and CI run without a clamd daemon and
  stay fully functional — the scan reports ``available=False`` and the
  existing type/size checks remain the gate.
- **Graceful fallback**: any failure (daemon down, socket timeout, library
  missing) degrades to ``available=False, clean=True``. A message is never
  *blocked* because the scanner was unreachable — it is only blocked on a
  *positive* detection, which is always available-first.
- The scan runs in-process on the uploaded bytes before anything is stored;
  nothing is written to disk until the file is clean.

Production: run clamav/clamd (free, open-source, self-hostable) and set
``CLAMAV_ENABLED=True`` + ``CLAMAV_HOST``/``CLAMAV_PORT``.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Outcome of one virus scan."""

    available: bool  # a scanner was reachable and answered
    clean: bool  # no virus detected (True when no scanner: nothing to flag)
    viruses: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return self.available and not self.clean


def _setting(name: str, default):
    return getattr(settings, name, default)


def _clamd_client():
    """A reachable clamd client, or None. Never raises."""
    try:
        import pyclamd
    except ImportError:
        return None
    try:
        client = pyclamd.ClamdNetworkSocket(
            _setting("CLAMAV_HOST", "127.0.0.1"),
            _setting("CLAMAV_PORT", 3310),
            timeout=_setting("CLAMAV_TIMEOUT_SECONDS", 10),
        )
        client.ping()
        return client
    except Exception as exc:
        logger.info("ClamAV unavailable (%s); skipping scan.", exc)
        return None


def scan_bytes(data: bytes) -> ScanResult:
    """Scan ``data`` with ClamAV. Never raises.

    ``CLAMAV_ENABLED=False`` (default) short-circuits to
    ``available=False, clean=True`` — callers treat this as 'no scanner,
    type/size checks still apply'.
    """
    if not _setting("CLAMAV_ENABLED", False):
        return ScanResult(available=False, clean=True)

    client = _clamd_client()
    if client is None:
        return ScanResult(available=False, clean=True)

    try:
        result = client.instream(io.BytesIO(data))
    except Exception as exc:
        logger.warning("ClamAV scan failed (%s); treating as clean.", exc)
        return ScanResult(available=False, clean=True)

    if result:  # {stream_name: virus_name}
        return ScanResult(available=True, clean=False, viruses=list(result.values()))
    return ScanResult(available=True, clean=True)
