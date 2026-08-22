"""Custom DRF throttles."""

from rest_framework.settings import api_settings
from rest_framework.throttling import (
    AnonRateThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


class TrustedClientIPMixin:
    """Key throttles on the real client IP even behind a proxy.

    DRF's default ``get_ident`` reads ``REMOTE_ADDR`` — behind a proxy that is
    the proxy's address for *every* user, so all traffic shares one bucket.
    ``config.ip.get_client_ip`` honours ``NUM_PROXIES`` (opt-in trust of
    ``X-Forwarded-For``); see its docstring for the security trade-off.
    """

    def get_ident(self, request):
        from config.ip import get_client_ip

        return get_client_ip(request)


class TrustedAnonRateThrottle(TrustedClientIPMixin, AnonRateThrottle):
    """AnonRateThrottle that keys on the proxy-resolved client IP."""


class TrustedUserRateThrottle(TrustedClientIPMixin, UserRateThrottle):
    """UserRateThrottle that keys on the proxy-resolved client IP."""


class TrustedScopedRateThrottle(TrustedClientIPMixin, ScopedRateThrottle):
    """ScopedRateThrottle that keys on the proxy-resolved client IP."""


class AuthRateThrottle(TrustedClientIPMixin, SimpleRateThrottle):
    """Per-IP throttle for authentication endpoints (login/register).

    Unlike ``AnonRateThrottle``, this always keys on the client IP — even for
    authenticated requests — so brute-force attempts cannot dodge the limit by
    presenting (or rotating) credentials. The rate is read from
    ``DEFAULT_THROTTLE_RATES['auth']``.

    ``get_rate`` is overridden to read the *live* ``api_settings`` instead of
    the class-level ``THROTTLE_RATES`` snapshot: DRF caches that dict at
    import time, so ``@override_settings(REST_FRAMEWORK=...)`` in tests would
    silently keep the old rate (and, worse, auth tests would share a stale
    10/hour bucket across the whole suite). Behaviour in production is
    identical — both read the same ``DEFAULT_THROTTLE_RATES['auth']``.
    """

    scope = "auth"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
