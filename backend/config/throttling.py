"""Custom DRF throttles."""

from rest_framework.throttling import SimpleRateThrottle


class AuthRateThrottle(SimpleRateThrottle):
    """Per-IP throttle for authentication endpoints (login/register).

    Unlike ``AnonRateThrottle``, this always keys on the client IP — even for
    authenticated requests — so brute-force attempts cannot dodge the limit by
    presenting (or rotating) credentials. The rate is read from
    ``DEFAULT_THROTTLE_RATES['auth']``.
    """

    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
