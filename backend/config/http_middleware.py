"""Shared HTTP middleware (Phase 16).

RequestCorrelationMiddleware
  Injects ``X-Request-ID`` into every response so support engineers and log
  parsers can trace a request through the entire stack.  If the client already
  sends a ``X-Request-ID`` header we echo it back (client-provided IDs are
  useful for end-to-end tracing through mobile apps and frontend SPAs);
  otherwise we generate a UUID4.

  The ID is also stashed on ``request.request_id`` so downstream code (views,
  serializers, task dispatch) can access it without scraping headers.

CacheControlHeadersMiddleware
  Adds ``Cache-Control`` headers optimised for the image pipeline:
  * Content-hashed variant filenames (``v_*.webp``) → ``immutable, max-age=31536000``
    so browsers never revalidate an image whose hash would change on update.
  * Other media/static files → ``public, max-age=300`` (5 min).
"""

from __future__ import annotations

import re
import uuid

from django.utils.deprecation import MiddlewareMixin

_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
_HASHED_VARIANT_RE = re.compile(r"/v_[^/]+\.webp$")


class RequestCorrelationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.request_id = request.META.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", None)
        if request_id and "X-Request-ID" not in response.headers:
            response["X-Request-ID"] = request_id
        return response


class CacheControlHeadersMiddleware(MiddlewareMixin):
    """Phase 16 — immutable cache for content-hashed image variants."""

    def process_response(self, request, response):
        path = getattr(request, "path", "")
        if _HASHED_VARIANT_RE.search(path):
            response["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/media/"):
            response["Cache-Control"] = "public, max-age=300"
        return response
