"""Privacy and data-protection utilities for Phase 17 Stage 8.

Provides:
- Sensitive-field masking for logs and API responses
- Reason sanitization for provider failures (prevent raw exception leaks)
- CSV-safe value formatting
- Audit logging for admin data access
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that indicate sensitive data
_PHONE_RE = re.compile(r"\b01[3-9]\d{8}\b")
_NID_RE = re.compile(r"\b\d{10,17}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PASSPORT_RE = re.compile(r"\b[A-Z]\d{8}\b")

# Fields that are always sensitive when present in dicts
SENSITIVE_FIELDS = {
    "phone",
    "national_id",
    "nid",
    "passport",
    "bank_account",
    "bank_account_number",
    "credit_card",
    "selfie",
    "face_match_selfie",
    "password",
    "otp",
    "token",
    "secret",
    "email",
}

# Maximum length for reason strings exposed in API responses
MAX_REASON_LENGTH = 200


def mask_phone(phone: str | None) -> str:
    """Mask a Bangladeshi phone number: 017****5678."""
    if not phone or len(phone) < 8:
        return phone or ""
    return phone[:4] + "*" * (len(phone) - 8) + phone[-4:]


def mask_nid(nid: str | None) -> str:
    """Mask a national ID: ****1234."""
    if not nid or len(nid) < 4:
        return nid or ""
    return "*" * (len(nid) - 4) + nid[-4:]


def mask_email(email: str | None) -> str:
    """Mask an email: u***@example.com."""
    if not email or "@" not in email:
        return email or ""
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return local[0] + "***@" + domain


def mask_value(key: str, value: Any) -> Any:
    """Return a masked version of value if the field is sensitive."""
    if value is None:
        return None
    key_lower = key.lower()
    if key_lower in SENSITIVE_FIELDS:
        if key_lower in ("phone",):
            return mask_phone(str(value))
        if key_lower in ("national_id", "nid"):
            return mask_nid(str(value))
        if key_lower in ("email",):
            return mask_email(str(value))
        return "***"
    return value


def sanitize_dict(data: dict) -> dict:
    """Return a copy of `data` with all sensitive field values masked."""
    return {k: mask_value(k, v) for k, v in data.items()}


def sanitize_reason(raw_reason: str) -> str:
    """Strip PII from a provider failure reason before exposing it.

    Preserves the diagnostic intent but removes phone numbers, NIDs,
    emails, and long exception chains that might leak internals.
    """
    if not raw_reason:
        return ""
    # Truncate
    clean = raw_reason[:MAX_REASON_LENGTH]
    # Mask phone numbers
    clean = _PHONE_RE.sub(lambda m: mask_phone(m.group()), clean)
    # Mask NIDs (10+ digit numbers that aren't phone numbers)
    clean = _NID_RE.sub(lambda m: mask_nid(m.group()), clean)
    # Mask emails
    clean = _EMAIL_RE.sub(lambda m: mask_email(m.group()), clean)
    # Remove file paths (might reveal server structure)
    clean = re.sub(r"[A-Z]:\\[^\s\"']+", "[path]", clean)
    clean = re.sub(r"/home/[^\s\"']+", "[path]", clean)
    clean = re.sub(r"/var/[^\s\"']+", "[path]", clean)
    return clean


def safe_log_dict(data: dict, prefix: str = "") -> dict:
    """Create a sanitized copy of `data` suitable for logging.

    Masks all sensitive fields and truncates long string values.
    """
    sanitized = sanitize_dict(data)
    for k, v in sanitized.items():
        if isinstance(v, str) and len(v) > 100:
            sanitized[k] = v[:100] + "..."
    if prefix:
        logger.debug("%s: %s", prefix, sanitized)
    return sanitized


def csv_safe_value(value: Any) -> str:
    """Format a value for CSV export, ensuring no injection.

    Wraps values containing commas, quotes, or newlines in quotes
    and escapes any embedded quotes.
    """
    if value is None:
        return ""
    s = str(value)
    if any(c in s for c in (",", '"', "\n", "\r")):
        return '"' + s.replace('"', '""') + '"'
    return s


def csv_safe_row(row: dict, sensitive_keys: set[str] | None = None) -> dict:
    """Return a copy of `row` with sensitive fields masked for CSV export."""
    if sensitive_keys is None:
        sensitive_keys = SENSITIVE_FIELDS
    safe = {}
    for k, v in row.items():
        if k.lower() in sensitive_keys:
            masked = mask_value(k, v) if k.lower() in SENSITIVE_FIELDS else "***"
            safe[k] = csv_safe_value(masked)
        else:
            safe[k] = csv_safe_value(v)
    return safe


def audit_log_access(user, resource_type: str, resource_id: Any, action: str):
    """Log an admin access to sensitive data for audit trail."""
    logger.info(
        "AUDIT: user=%s action=%s resource=%s/%s",
        getattr(user, "pk", "unknown"),
        action,
        resource_type,
        resource_id,
    )
