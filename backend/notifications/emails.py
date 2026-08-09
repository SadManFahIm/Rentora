"""Transactional email helper — brand-consistent HTML emails.

Every product email (OTP codes, booking updates, fraud flags, promotion
expiry) is rendered from a template under ``notifications/templates/emails/``
and sent as a multipart message: a plain-text fallback plus the styled HTML,
so even the most aggressive email client shows something sensible.

``send_html_email`` never raises on send failure (``fail_silently=True``) —
email is a best-effort channel and an OTP failure must not break a login.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_html_email(
    subject: str,
    to_email: str,
    template_name: str,
    context: dict[str, Any] | None = None,
    from_email: str | None = None,
) -> int:
    """Render and send one brand-styled HTML email.

    Parameters
    ----------
    subject:
        Email subject line.
    to_email:
        Recipient address. Empty recipients are skipped (no-op, returns 0).
    template_name:
        Template under ``notifications/templates/emails/`` (no extension).
    context:
        Template context; ``site_name`` is always merged in.
    from_email:
        Override the default ``DEFAULT_FROM_EMAIL``.

    Returns
    -------
    int
        Number of emails sent (0 or 1).
    """
    if not to_email:
        return 0

    full_context: dict[str, Any] = {
        "site_name": getattr(settings, "SITE_NAME", "Rentora"),
        **(context or {}),
    }
    html_body = render_to_string(f"emails/{template_name}.html", full_context)
    plain_body = render_to_string(f"emails/{template_name}.txt", full_context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=from_email or getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        to=[to_email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=True)
