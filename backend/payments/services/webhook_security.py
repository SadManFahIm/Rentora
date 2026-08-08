"""Generic webhook-hardening helpers, shared across gateway integrations.

Neither SSLCommerz nor bKash sign their callbacks (see PaymentSuccess/Fail/
CancelCallbackView and BkashCallbackView in payments/views.py) — the real
protection there is re-validating against the gateway's own API
(``validate_payment`` / ``query_payment``), never trusting the callback body.

This module adds two independent, defense-in-depth layers on top of that:

1. An HMAC signature verifier, generic and reusable, for any *future* gateway
   that does sign its webhooks.
2. A source-IP allowlist check that only ever logs on a mismatch in sandbox
   mode (sandbox source IPs aren't published and vary), but can be made to
   reject traffic once a gateway's real IP ranges are known and configured.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def compute_hmac_signature(payload: bytes, secret: str, *, algorithm: str = "sha256") -> str:
    """Return the hex-encoded HMAC of ``payload`` under ``secret``."""
    digestmod = getattr(hashlib, algorithm)
    return hmac.new(secret.encode("utf-8"), payload, digestmod).hexdigest()


def verify_hmac_signature(
    payload: bytes, signature: str, secret: str, *, algorithm: str = "sha256"
) -> bool:
    """Constant-time check that ``signature`` matches ``payload`` under ``secret``.

    Always use this (never ``==``) to compare signatures — a naive string
    comparison leaks timing information an attacker can use to forge a valid
    signature byte-by-byte.
    """
    if not signature:
        return False
    expected = compute_hmac_signature(payload, secret, algorithm=algorithm)
    return hmac.compare_digest(expected, signature)


def get_client_ip(request) -> str:
    """Best-effort client IP, preferring a proxy-set X-Forwarded-For."""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def check_webhook_ip(request, *, allowlist: list[str], sandbox: bool, gateway: str) -> bool:
    """Return whether this webhook request should be processed.

    - No allowlist configured -> always allowed (nothing to check against).
    - IP matches the allowlist -> allowed.
    - IP doesn't match -> always logged as a warning; only actually rejected
      when ``sandbox`` is False, since sandbox environments' outbound IPs
      aren't published and are known to vary.
    """
    if not allowlist:
        return True

    client_ip = get_client_ip(request)
    if client_ip in allowlist:
        return True

    logger.warning("Webhook for %s received from unexpected IP: %s", gateway, client_ip)
    return sandbox
