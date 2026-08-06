"""Project-wide DRF exception handling.

Normalises every API error into a single, predictable envelope so clients can
rely on one shape regardless of which error occurred::

    {
        "success": false,
        "message": "<human-readable summary>",
        "errors": ["<detail>", "<detail>", ...]
    }

Handled explicitly: 400 (validation), 401, 403, 404, 405, 429 and any other
DRF ``APIException``. Anything DRF does not turn into a ``Response`` (i.e. an
unhandled server error) is caught and returned as a clean 500 instead of
leaking a stack trace.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# Fallback summary messages per status code.
_DEFAULT_MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "Invalid request.",
    status.HTTP_401_UNAUTHORIZED: "Authentication credentials were not provided or are invalid.",
    status.HTTP_403_FORBIDDEN: "You do not have permission to perform this action.",
    status.HTTP_404_NOT_FOUND: "The requested resource was not found.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method not allowed.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests. Please slow down and try again later.",
}


def _flatten_errors(detail: Any, prefix: str = "") -> list[str]:
    """Flatten DRF's nested error ``detail`` into a flat list of strings.

    Field errors are rendered as ``"field: message"``; list and scalar errors
    are rendered as-is. This keeps the ``errors`` array easy to display without
    the client having to walk an arbitrary tree.
    """
    messages: list[str] = []

    if isinstance(detail, dict):
        for key, value in detail.items():
            label = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            messages.extend(_flatten_errors(value, prefix=label))
    elif isinstance(detail, (list, tuple)):
        for item in detail:
            messages.extend(_flatten_errors(item, prefix=prefix))
    else:
        text = str(detail)
        messages.append(f"{prefix}: {text}" if prefix else text)

    return messages


def custom_exception_handler(exc: Exception, context: dict) -> Response:
    """DRF ``EXCEPTION_HANDLER`` returning the unified error envelope.

    Delegates to DRF's default handler first (so auth/throttle/validation
    semantics, headers like ``Retry-After`` and ``WWW-Authenticate`` are
    preserved), then reshapes the body. Uncaught exceptions become a 500.
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        # DRF did not recognise this exception → genuine server error.
        logger.exception("Unhandled exception in API request", exc_info=exc)
        return Response(
            {
                "success": False,
                "message": "An unexpected server error occurred. Please try again later.",
                "errors": ["internal_server_error"],
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    errors = _flatten_errors(response.data)
    message = _DEFAULT_MESSAGES.get(response.status_code)
    if message is None:
        # Use the first concrete error as the summary when we have no default.
        message = errors[0] if errors else "Request failed."

    response.data = {
        "success": False,
        "message": message,
        "errors": errors,
    }
    return response
