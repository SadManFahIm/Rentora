"""Security headers middleware (Tier-1 quick win).

Adds the hardening headers that push Lighthouse "Best Practices" and general
defense-in-depth to 100:

- ``Content-Security-Policy`` — sourced from ``SECURITY_CONTENT_SECURITY_POLICY``
  (a dict of directive -> value). The default allows the Django admin and the
  drf-spectacular docs (inline styles/scripts + their CDN assets) while
  blocking third-party frames, objects and base-URI tricks.
- ``Referrer-Policy: strict-origin-when-cross-origin`` — no full URLs leak to
  third-party origins; same-origin stays functional.
- ``Permissions-Policy`` — camera/microphone/geolocation disabled by default
  (this is an API + admin, not a media capture app).
- ``Strict-Transport-Security`` — only when ``SECURE_HSTS_SECONDS`` is set
  (prod.py), never in local dev over plain HTTP.

Headers are applied to *every* response (API JSON included — harmless there,
valuable on the admin/docs/media pages). The Vite SPA is a separate origin
and sets its own headers, so this never touches the frontend.
"""

from django.utils.deprecation import MiddlewareMixin


class SecurityHeadersMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Sniffing protection: browsers must not guess a content type.
        response["X-Content-Type-Options"] = "nosniff"

        csp = self._csp()
        if csp:
            response["Content-Security-Policy"] = "; ".join(
                f"{directive} {value}" for directive, value in csp.items()
            )

        referrer = self._setting("SECURITY_REFERRER_POLICY", "strict-origin-when-cross-origin")
        response["Referrer-Policy"] = referrer

        permissions = self._setting(
            "SECURITY_PERMISSIONS_POLICY", "camera=(), microphone=(), geolocation=()"
        )
        response["Permissions-Policy"] = permissions

        hsts_seconds = self._setting("SECURE_HSTS_SECONDS", 0)
        if hsts_seconds:
            response["Strict-Transport-Security"] = f"max-age={int(hsts_seconds)}"

        return response

    @staticmethod
    def _setting(name, default):
        from django.conf import settings

        return getattr(settings, name, default)

    def _csp(self):
        from django.conf import settings

        return getattr(settings, "SECURITY_CONTENT_SECURITY_POLICY", None)
