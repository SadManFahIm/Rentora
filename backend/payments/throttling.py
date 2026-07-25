"""Payment-specific DRF throttles (mirrors config/throttling.py's AuthRateThrottle)."""

from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class PaymentInitiateRateThrottle(UserRateThrottle):
    """Caps how often one authenticated user can start a payment session.

    Rate is read from ``DEFAULT_THROTTLE_RATES['payment_initiate']``
    (5/hour) — far tighter than the general "user" scope, since starting a
    payment session is a much more sensitive, gateway-facing operation than
    an ordinary API call.
    """

    scope = "payment_initiate"


class WebhookCallbackRateThrottle(SimpleRateThrottle):
    """Per-IP throttle for gateway callback endpoints.

    These views use `AllowAny`/no auth (the gateway itself hits them, not a
    logged-in user), so throttling must key on IP rather than user — same
    approach as `config.throttling.AuthRateThrottle`. Rate is read from
    ``DEFAULT_THROTTLE_RATES['webhook_callback']`` (20/minute), loose enough
    to absorb legitimate gateway retries while still capping flood/replay
    attempts against an endpoint that has no session to rate-limit by.
    """

    scope = "webhook_callback"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
