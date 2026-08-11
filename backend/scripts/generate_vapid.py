"""Generate a Web Push VAPID key pair for Rentora.

Run once (offline, no server needed) and put the values into your
environment:

    python scripts/generate_vapid.py

Prints the private key (backend: VAPID_PRIVATE_KEY), the public key (backend:
VAPID_PUBLIC_KEY, frontend: VITE_VAPID_PUBLIC_KEY) and a ready-to-paste
`.env` snippet. The public key is not a secret — it ships in the frontend
bundle so the browser can build the push subscription.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Importing the settings module registers pywebpush's VAPID tools.
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from py_vapid import Vapid02


def main() -> None:
    vapid = Vapid02()
    vapid.generate_keys()
    private_key = vapid.private_key  # bytes
    public_key = vapid.public_key  # bytes

    import base64

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    priv = b64url(private_key)
    pub = b64url(public_key)

    print("VAPID key pair generated — paste into your backend env:\n")
    print(f"VAPID_PRIVATE_KEY={priv}")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print("VAPID_SUBJECT=mailto:admin@rentora.com")
    print("\nFrontend build env (.env.local):")
    print(f"VITE_VAPID_PUBLIC_KEY={pub}")
    print("\n(Keys are base64url-encoded raw bytes; pywebpush expects exactly this format.)")


if __name__ == "__main__":
    main()
