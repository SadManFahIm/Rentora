"""Web Push (browser notification) delivery for Rentora notifications.

Every in-app notification (booking update, chat message, fraud flag, KYC
decision, …) is also pushed to the recipient's subscribed browsers via the
Web Push protocol — the same channel Chrome/Firefox/Edge use for news sites.
Zero-cost push: no third-party service beyond the browser vendors' own push
services, no per-message fees.

Setup
-----
1. Generate a VAPID key pair once::

       python scripts/generate_vapid.py

2. Set ``VAPID_PUBLIC_KEY`` / ``VAPID_PRIVATE_KEY`` (and optionally
   ``VAPID_SUBJECT``) in the environment — the public key also goes into the
   frontend build as ``VITE_VAPID_PUBLIC_KEY`` so the browser can subscribe.

If VAPID keys are unset this module is a safe no-op: sending is skipped, so
local dev and CI never touch a push service.
"""

from __future__ import annotations

import json
import logging
import urllib.error

from django.conf import settings
from pywebpush import WebPushException, webpush

from .models import PushSubscription

logger = logging.getLogger(__name__)

# The Web Push spec requires a mailto: or https: contact on every payload.
_DEFAULT_SUBJECT = "mailto:admin@rentora.com"


def vapid_private_key() -> str | None:
    key = getattr(settings, "VAPID_PRIVATE_KEY", "")
    return key or None


def vapid_public_key() -> str | None:
    key = getattr(settings, "VAPID_PUBLIC_KEY", "")
    return key or None


def vapid_subject() -> str:
    return getattr(settings, "VAPID_SUBJECT", "") or _DEFAULT_SUBJECT


def _vapid_claims() -> dict[str, str]:
    return {"sub": vapid_subject(), "aud": "https://push.services.mozilla.com"}


def send_push(subscription: PushSubscription, title: str, body: str, url: str = "") -> bool:
    """Deliver one push notification to a subscription. Returns success.

    Never raises: a push failure must not break the caller (notification
    creation, a signal handler, a Celery task). A subscription that the push
    service reports gone (410) is deleted so we stop paying for dead weight.
    """
    if vapid_private_key() is None or vapid_public_key() is None:
        logger.debug("VAPID not configured — skipping push to %s", subscription.endpoint[:40])
        return False

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "icon": getattr(settings, "PUSH_ICON_URL", ""),
        "badge": getattr(settings, "PUSH_BADGE_URL", ""),
    }

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"auth": subscription.auth, "p256dh": subscription.p256dh},
            },
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key(),
            vapid_claims=_vapid_claims(),
        )
        return True
    except WebPushException as exc:
        # 410 Gone — the browser dropped the subscription (cleared site data,
        # revoked permission). Forget it so we don't retry forever.
        if exc.response is not None and exc.response.status_code == 410:
            logger.info("Removing dead push subscription %s (410)", subscription.endpoint[:40])
            subscription.delete()
        else:
            logger.warning("Push to %s failed: %s", subscription.endpoint[:40], exc)
        return False
    except urllib.error.URLError as exc:
        logger.warning("Push to %s unreachable: %s", subscription.endpoint[:40], exc)
        return False


def send_push_to_user(user, title: str, body: str, url: str = "") -> int:
    """Push a notification to every live subscription the user owns.

    Returns the number of subscriptions successfully notified.
    """
    sent = 0
    for subscription in PushSubscription.objects.filter(user=user):
        if send_push(subscription, title, body, url):
            sent += 1
    return sent
