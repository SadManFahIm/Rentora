"""SSLCommerz payment gateway integration (sandbox).

Two calls matter here:

- ``initiate_payment`` opens a payment "session" with SSLCommerz and gets
  back a gateway URL the client is redirected to, to actually pay.
- ``validate_payment`` re-confirms a transaction against SSLCommerz's own
  records. This is what protects us from a forged/spoofed callback: anyone
  can POST a fake "success" payload at our callback URL, but they cannot
  make SSLCommerz's *validation* API agree that the transaction succeeded.

Both are plain ``requests`` calls against the documented sandbox REST API
(no SDK) — sslcommerz-lib bundles very little logic on top of two POSTs and
pulls in an unmaintained dependency, so raw requests is more transparent and
easier to keep sandbox-only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests
from django.conf import settings

if TYPE_CHECKING:
    from payments.models import Payment

logger = logging.getLogger(__name__)

SANDBOX_SESSION_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
SANDBOX_VALIDATION_URL = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"
SANDBOX_REFUND_URL = "https://sandbox.sslcommerz.com/validator/api/refundAPI.php"
LIVE_SESSION_URL = "https://securepay.sslcommerz.com/gwprocess/v4/api.php"
LIVE_VALIDATION_URL = "https://securepay.sslcommerz.com/validator/api/validationserverAPI.php"
LIVE_REFUND_URL = "https://securepay.sslcommerz.com/validator/api/refundAPI.php"

REQUEST_TIMEOUT_SECONDS = 15


class SSLCommerzError(Exception):
    """Raised when SSLCommerz rejects a request or is unreachable."""


def _session_url() -> str:
    return SANDBOX_SESSION_URL if settings.SSLCOMMERZ_IS_SANDBOX else LIVE_SESSION_URL


def _validation_url() -> str:
    return SANDBOX_VALIDATION_URL if settings.SSLCOMMERZ_IS_SANDBOX else LIVE_VALIDATION_URL


def _refund_url() -> str:
    return SANDBOX_REFUND_URL if settings.SSLCOMMERZ_IS_SANDBOX else LIVE_REFUND_URL


def initiate_payment(
    payment: Payment, success_url: str, fail_url: str, cancel_url: str
) -> dict[str, Any]:
    """Open a payment session for ``payment`` and return the gateway redirect URL.

    ``payment.amount`` is used verbatim — callers must have already derived
    it from the booking server-side, never from client input.
    """
    tenant = payment.user

    payload = {
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "total_amount": str(payment.amount),
        "currency": "BDT",
        "tran_id": payment.transaction_id,
        "success_url": success_url,
        "fail_url": fail_url,
        "cancel_url": cancel_url,
        "cus_name": tenant.get_full_name() or tenant.username,
        "cus_email": tenant.email or "no-reply@rentora.local",
        "cus_phone": tenant.phone or "01700000000",
        "cus_add1": "Dhaka",
        "cus_city": "Dhaka",
        "cus_country": "Bangladesh",
        "shipping_method": "NO",
        "product_name": f"Booking #{payment.booking_id} - {payment.get_payment_type_display()}",
        "product_category": "Rent",
        "product_profile": "general",
    }

    try:
        response = requests.post(_session_url(), data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("SSLCommerz initiate_payment failed for %s: %s", payment.transaction_id, exc)
        raise SSLCommerzError(f"Could not reach SSLCommerz: {exc}") from exc

    if data.get("status") != "SUCCESS":
        logger.error(
            "SSLCommerz rejected session for %s: %s",
            payment.transaction_id,
            data.get("failedreason") or data,
        )
        raise SSLCommerzError(
            data.get("failedreason") or "SSLCommerz rejected the payment session."
        )

    return data


def validate_payment(val_id: str) -> dict[str, Any]:
    """Ask SSLCommerz to confirm ``val_id`` is a genuine, successful transaction.

    Always call this before trusting a success callback — the callback body
    itself is client-supplied and trivially forgeable.
    """
    params = {
        "val_id": val_id,
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "format": "json",
    }

    try:
        response = requests.get(_validation_url(), params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("SSLCommerz validate_payment failed for val_id=%s: %s", val_id, exc)
        raise SSLCommerzError(f"Could not validate payment with SSLCommerz: {exc}") from exc


def refund_payment(
    bank_tran_id: str, refund_amount: str, refund_remarks: str = "Refund requested by landlord"
) -> dict[str, Any]:
    """Request a refund for a previously validated transaction.

    ``bank_tran_id`` is SSLCommerz's own transaction reference (stored on the
    Payment as ``gateway_transaction_id`` once ``validate_payment`` confirms
    a success) — refunds are only ever issued against a genuinely-settled
    transaction, never a bare merchant ``tran_id``.
    """
    payload = {
        "bank_tran_id": bank_tran_id,
        "refund_amount": str(refund_amount),
        "refund_remarks": refund_remarks,
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "format": "json",
    }

    try:
        response = requests.post(_refund_url(), data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.error("SSLCommerz refund_payment failed for bank_tran_id=%s: %s", bank_tran_id, exc)
        raise SSLCommerzError(f"Could not process SSLCommerz refund: {exc}") from exc

    if data.get("status") not in ("success", "processing"):
        logger.error("SSLCommerz rejected refund for bank_tran_id=%s: %s", bank_tran_id, data)
        raise SSLCommerzError(data.get("errorReason") or "SSLCommerz rejected the refund request.")

    return data
