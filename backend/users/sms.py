"""SMS delivery provider abstraction (Phase 13 — SMS OTP login).

Follows the same pluggable-provider pattern as the KYC automation
(``users/kyc_provider.py``): a ``SMS_PROVIDER`` setting selects the
implementation and the master switch is ``SMS_OTP_ENABLED`` (OFF by default,
so a deployment only exposes phone sign-in once it has a real gateway).

Providers:

- ``console`` (default) — logs the code to the server log. Local dev and CI
  work with zero configuration; the code is visible in ``runserver`` output.
- ``http`` — POSTs a generic gateway (``SMS_GATEWAY_URL`` / ``SMS_GATEWAY_API_KEY``
  / ``SMS_SENDER_ID``). A real provider (Twilio, GreenWeb, bKash SMS API…)
  plugs in behind the same ``send(phone, code)`` contract.

Delivery never raises: SMS is a best-effort channel and must never break the
auth flow, so provider failures are logged and swallowed.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Bangladeshi mobile operators share the 1[3-9] prefix range (13-19).
_BD_NUMBER_RE = re.compile(r"1[3-9]\d{8}$")


def normalize_bd_phone(raw: str) -> str | None:
    """Normalize a Bangladeshi mobile number to E.164 ``+8801XXXXXXXXX``.

    Accepts ``01XXXXXXXXX`` (11 digits), ``8801XXXXXXXXX`` (13 digits) and
    ``+8801XXXXXXXXX`` (with the leading ``+``). Returns ``None`` for any
    number that isn't a plausible BD mobile number, so the serializer can
    reject junk up front.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("880"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or not _BD_NUMBER_RE.fullmatch(digits):
        return None
    return f"+880{digits}"


def mask_phone(phone: str) -> str:
    """``+8801712345678`` → ``+8801••••••78`` (last two digits visible)."""
    if len(phone) >= 8:
        return f"{phone[:5]}••••{phone[-2:]}"
    return phone


class ConsoleSmsProvider:
    """Logs the code to the server log — zero-config local dev / CI."""

    name = "console"

    def send(self, phone: str, code: str) -> None:
        logger.warning("[SMS] verification code for %s: %s", phone, code)


class HttpSmsProvider:
    """Generic HTTP gateway POST (the shape most BD SMS APIs accept).

    Configure ``SMS_GATEWAY_URL``, ``SMS_GATEWAY_API_KEY`` and
    ``SMS_SENDER_ID``. The exact payload contract depends on the provider —
    override ``payload()``/``headers()`` for a specific gateway.
    """

    name = "http"

    def __init__(self) -> None:
        self.url = getattr(settings, "SMS_GATEWAY_URL", "")
        self.api_key = getattr(settings, "SMS_GATEWAY_API_KEY", "")
        self.sender_id = getattr(settings, "SMS_SENDER_ID", "")

    def send(self, phone: str, code: str) -> None:
        if not self.url:
            logger.warning(
                "[SMS] SMS_PROVIDER=http but SMS_GATEWAY_URL is empty — falling back to console log."
            )
            logger.warning("[SMS] verification code for %s: %s", phone, code)
            return
        import requests

        try:
            resp = requests.post(
                self.url,
                json={
                    "to": phone,
                    "message": f"Your Rentora verification code is {code}. It expires in 10 minutes.",
                    "sender_id": self.sender_id,
                    "api_key": self.api_key,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as exc:  # SMS must never break auth
            logger.warning("[SMS] http provider failed for %s: %s", phone, exc)


_PROVIDERS = {
    "console": ConsoleSmsProvider,
    "http": HttpSmsProvider,
}


def get_provider() -> ConsoleSmsProvider | HttpSmsProvider:
    """The configured provider, or the console provider for anything unknown."""
    name = (getattr(settings, "SMS_PROVIDER", "") or "console").strip().lower()
    provider_cls = _PROVIDERS.get(name, ConsoleSmsProvider)
    return provider_cls()


def sms_otp_enabled() -> bool:
    """Master switch — OFF unless a deployment explicitly enables it."""
    return bool(getattr(settings, "SMS_OTP_ENABLED", False))


def send_sms(phone: str, code: str) -> None:
    """Deliver a code via the active provider. Never raises."""
    try:
        get_provider().send(phone, code)
    except Exception:
        logger.exception("SMS delivery failed for %s", phone)
