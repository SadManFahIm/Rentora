"""bKash Tokenized Checkout integration (sandbox).

Flow: grant a short-lived token -> create a payment session (get a bkashURL
to redirect the user to) -> user pays on bKash's page -> bKash redirects back
to our callback with a paymentID -> we *query* bKash for the real status
(never trust the callback's query params alone) -> if genuinely completed,
*execute* the payment to finalize it.

The grant token is cached (it's valid for a while and re-requesting it on
every call would be wasteful and could hit sandbox rate limits); everything
else is a plain ``requests`` call against the documented sandbox REST API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests
from django.conf import settings
from django.core.cache import cache

if TYPE_CHECKING:
    from payments.models import Payment

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15
GRANT_TOKEN_CACHE_KEY = "bkash_grant_token"
# Refresh a bit before the token actually expires so an in-flight request
# never gets caught using a token that expires mid-call.
TOKEN_EXPIRY_BUFFER_SECONDS = 60


class BkashError(Exception):
    """Raised when bKash rejects a request or is unreachable."""


def _base_url() -> str:
    return settings.BKASH_SANDBOX_BASE_URL.rstrip("/")


def get_grant_token(force_refresh: bool = False) -> str:
    """Return a valid bKash access token, fetching + caching a new one if needed."""
    if not force_refresh:
        cached = cache.get(GRANT_TOKEN_CACHE_KEY)
        if cached:
            return cached

    payload = {
        "app_key": settings.BKASH_APP_KEY,
        "app_secret": settings.BKASH_APP_SECRET,
    }
    headers = {
        "username": settings.BKASH_USERNAME,
        "password": settings.BKASH_PASSWORD,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            f"{_base_url()}/tokenized/checkout/token/grant",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("bKash grant token request failed: %s", exc)
        raise BkashError(f"Could not obtain bKash grant token: {exc}") from exc

    token = data.get("id_token")
    if not token:
        logger.error("bKash grant token response missing id_token: %s", data)
        raise BkashError(data.get("statusMessage") or "bKash did not return a grant token.")

    expires_in = int(data.get("expires_in", 3600))
    ttl = max(expires_in - TOKEN_EXPIRY_BUFFER_SECONDS, 30)
    cache.set(GRANT_TOKEN_CACHE_KEY, token, timeout=ttl)

    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": token,
        "X-APP-Key": settings.BKASH_APP_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post(
    path: str, payload: dict[str, Any], *, retry_on_auth_error: bool = True
) -> dict[str, Any]:
    token = get_grant_token()
    try:
        response = requests.post(
            f"{_base_url()}{path}",
            json=payload,
            headers=_auth_headers(token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("bKash POST %s failed: %s", path, exc)
        raise BkashError(f"bKash request to {path} failed: {exc}") from exc

    # A stale cached token yields a 401-ish "token invalid" statusCode from
    # bKash rather than an HTTP 401; retry once with a forced-fresh token.
    if data.get("statusCode") == "0001" and retry_on_auth_error:
        get_grant_token(force_refresh=True)
        return _post(path, payload, retry_on_auth_error=False)

    return data


def create_payment(payment: Payment, callback_url: str) -> dict[str, Any]:
    """Open a bKash checkout session for ``payment`` and return the session data
    (including ``bkashURL`` to redirect the user to and ``paymentID``)."""
    payload = {
        "mode": "0011",
        "payerReference": str(payment.user_id),
        "callbackURL": callback_url,
        "amount": str(payment.amount),
        "currency": "BDT",
        "intent": "sale",
        "merchantInvoiceNumber": payment.transaction_id,
    }

    data = _post("/tokenized/checkout/create", payload)

    if data.get("statusCode") not in ("0000", None) and "paymentID" not in data:
        logger.error("bKash create_payment rejected for %s: %s", payment.transaction_id, data)
        raise BkashError(data.get("statusMessage") or "bKash rejected the payment session.")

    if "paymentID" not in data:
        raise BkashError("bKash did not return a paymentID.")

    return data


def execute_payment(payment_id: str) -> dict[str, Any]:
    """Finalize a payment after the user completes it on bKash's page."""
    return _post("/tokenized/checkout/execute", {"paymentID": payment_id})


def query_payment(payment_id: str) -> dict[str, Any]:
    """Ask bKash for the authoritative current status of ``payment_id``.

    Always call this before trusting a callback's query-string status — the
    callback URL is hit by the user's own browser, so its params are just as
    forgeable as any other client-supplied data.
    """
    token = get_grant_token()
    try:
        response = requests.get(
            f"{_base_url()}/tokenized/checkout/payment/status/{payment_id}",
            headers=_auth_headers(token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("bKash query_payment failed for %s: %s", payment_id, exc)
        raise BkashError(f"Could not query bKash payment status: {exc}") from exc


def refund_payment(
    payment_id: str,
    trx_id: str,
    amount: str,
    *,
    sku: str = "refund",
    reason: str = "requested by customer",
) -> dict[str, Any]:
    """Refund a previously executed bKash transaction.

    Raises on any error response — a caller must never treat a bare "no
    exception" as proof of a successful refund, since bKash reports failures
    (e.g. an invalid/expired paymentID) as HTTP 200 with an error `statusCode`
    rather than a non-2xx status.
    """
    payload = {
        "paymentID": payment_id,
        "amount": str(amount),
        "trxID": trx_id,
        "sku": sku,
        "reason": reason,
    }
    data = _post("/tokenized/checkout/payment/refund", payload)

    status_code = data.get("statusCode")
    if (status_code is not None and status_code != "0000") or "refundTrxID" not in data:
        logger.error("bKash refund_payment rejected for paymentID=%s: %s", payment_id, data)
        raise BkashError(data.get("statusMessage") or "bKash rejected the refund request.")

    return data
