"""Storage backends (Phase 16).

``PrivateMediaStorage`` is a ``FileSystemStorage`` rooted OUTSIDE the public
``MEDIA_ROOT`` and with ``base_url=None``, so sensitive uploads (KYC / tenant
documents) are never reachable through the public media URL — even under
Django's DEBUG static-file serving. They are served only through the
authenticated document endpoints (users.views.KycDocumentFileView /
TenantVerificationFileView), which enforce owner-or-admin access.
"""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Filesystem storage for private uploads, outside the public media root."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("location", settings.MEDIA_PRIVATE_ROOT)
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)


private_media_storage = PrivateMediaStorage()
