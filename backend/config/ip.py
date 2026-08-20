"""Client-IP resolution for behind-proxy deployments (Phase 16).

DRF throttling keys on ``REMOTE_ADDR`` by default — which behind any proxy or
load balancer is *every* user's address, collapsing the entire site into one
rate-limit bucket. ``get_client_ip`` resolves the real client IP from
``X-Forwarded-For`` only when the deployment declares how many trusted proxies
sit in front of the app via ``NUM_PROXIES``:

* ``NUM_PROXIES = 0`` (default): the app is directly reachable — ``XFF`` is
  ignored entirely, so a client can't spoof its throttle identity.
* ``NUM_PROXIES = N``: the rightmost ``N`` entries of ``XFF`` are trusted
  proxy hops; the client IP is the one immediately before them.

Tuning it wrong is unsafe in the other direction (trusting an attacker's
header when there is no proxy lets them rotate throttle buckets), which is why
the default is opt-in rather than always parsing ``XFF``.
"""

from __future__ import annotations

from django.conf import settings


def get_client_ip(request) -> str:
    """Return the client IP, honouring a configured trusted proxy count."""
    num_proxies = int(getattr(settings, "NUM_PROXIES", 0) or 0)
    if num_proxies > 0:
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            parts = [part.strip() for part in forwarded_for.split(",") if part.strip()]
            if parts:
                # parts[-1] was appended by the last proxy = our immediate
                # peer; the client is the entry `num_proxies` hops before it.
                idx = max(len(parts) - num_proxies, 0)
                if idx < len(parts):
                    return parts[idx]
    return request.META.get("REMOTE_ADDR", "")
