"""WebAuthn / FIDO2 passkey service (py_webauthn).

Implements the server side of the two ceremonies:

- **Registration** — an authenticated user creates a passkey on their
  authenticator; we store the public key (never the private key).
- **Authentication** — a passkey assertion is verified and, on success, the
  user is identified by the credential and issued JWTs.

Challenges are stored in the Django cache (LocMemCache in dev, Redis in
prod) with a short TTL and consumed on verification. ``rp_id`` and
``origin`` are configured in settings and must match the browser's origin
(``localhost`` works for local development; a shared registrable domain is
required in production).
"""

import json
import secrets

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from webauthn import (
    generate_authentication_options as _wa_generate_auth_options,
)
from webauthn import (
    generate_registration_options as _wa_generate_reg_options,
)
from webauthn import (
    verify_authentication_response as _wa_verify_auth_response,
)
from webauthn import (
    verify_registration_response as _wa_verify_reg_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.exceptions import InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import PasskeyCredential

CHALLENGE_TTL_SECONDS = 5 * 60
_REG_CHALLENGE_KEY = "passkey_reg_{user_id}"
_LOGIN_CHALLENGE_KEY = "passkey_login_{challenge_id}"


def _rp_id() -> str:
    return getattr(settings, "WEBAUTHN_RP_ID", "localhost")


def _rp_name() -> str:
    return getattr(settings, "WEBAUTHN_RP_NAME", "Rentora")


def _origin() -> str:
    return getattr(settings, "WEBAUTHN_ORIGIN", "http://localhost:3000")


def _credential_descriptors(user) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in PasskeyCredential.objects.filter(user=user)
    ]


# ============================================================
# Registration
# ============================================================


def generate_registration_options(user) -> dict:
    """Build the options payload for ``navigator.credentials.create``."""
    options = _wa_generate_reg_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=secrets.token_bytes(16),
        user_name=user.username or user.email,
        user_display_name=(user.first_name or user.username or user.email)[:64],
        exclude_credentials=_credential_descriptors(user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    cache.set(
        _REG_CHALLENGE_KEY.format(user_id=user.pk),
        options.challenge,
        timeout=CHALLENGE_TTL_SECONDS,
    )
    return json.loads(options_to_json(options))


def verify_registration_response(user, response: dict, name: str = "") -> dict:
    """Validate the authenticator's registration response and store the key."""
    challenge = cache.get(_REG_CHALLENGE_KEY.format(user_id=user.pk))
    if not challenge:
        raise InvalidRegistrationResponse("Registration challenge expired — please retry.")

    verification = _wa_verify_reg_response(
        credential=response,
        expected_challenge=challenge,
        expected_origin=_origin(),
        expected_rp_id=_rp_id(),
    )
    if not verification.verified or verification.credential_id is None:
        raise InvalidRegistrationResponse("Registration could not be verified.")

    cred = verification.credential
    credential_id = bytes_to_base64url(cred.id)
    PasskeyCredential.objects.create(
        user=user,
        credential_id=credential_id,
        public_key=bytes_to_base64url(cred.public_key),
        sign_count=cred.sign_count,
        transports=response.get("response", {}).get("transports", []) or [],
        name=name[:120],
    )
    cache.delete(_REG_CHALLENGE_KEY.format(user_id=user.pk))
    return {"verified": True, "credential_id": credential_id}


# ============================================================
# Authentication (passwordless login)
# ============================================================


def generate_authentication_options() -> dict:
    """Build options for a discoverable-credential assertion.

    ``allow_credentials`` is omitted so the browser can offer any passkey
    registered to this RP (conditional UI). The opaque ``challenge_id`` is
    returned alongside so the client can reference it at completion.
    """
    options = _wa_generate_auth_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_id = secrets.token_urlsafe(24)
    cache.set(
        _LOGIN_CHALLENGE_KEY.format(challenge_id=challenge_id),
        options.challenge,
        timeout=CHALLENGE_TTL_SECONDS,
    )
    payload = json.loads(options_to_json(options))
    payload["challenge_id"] = challenge_id
    return payload


def verify_authentication_response(challenge_id: str, response: dict) -> PasskeyCredential:
    """Verify an assertion; returns the matching credential on success."""
    challenge = cache.get(_LOGIN_CHALLENGE_KEY.format(challenge_id=challenge_id))
    if not challenge:
        raise InvalidRegistrationResponse("Sign-in challenge expired — please try again.")

    credential_id = response.get("id")
    if not credential_id:
        raise InvalidRegistrationResponse("Missing credential id.")
    try:
        credential = PasskeyCredential.objects.get(credential_id=credential_id)
    except PasskeyCredential.DoesNotExist as exc:
        raise InvalidRegistrationResponse("This passkey is not registered.") from exc

    verification = _wa_verify_auth_response(
        credential={
            "id": base64url_to_bytes(credential.credential_id),
            "public_key": base64url_to_bytes(credential.public_key),
            "sign_count": credential.sign_count,
        },
        authentication_response=response,
        expected_challenge=challenge,
        expected_origin=_origin(),
        expected_rp_id=_rp_id(),
    )
    if not verification.verified:
        raise InvalidRegistrationResponse("Passkey assertion could not be verified.")

    # Replay/clone protection: authenticators increment the counter; a
    # static-zero counter is reported by some privacy-focused authenticators
    # and is handled per spec by skipping the check in that case.
    new_count = verification.new_sign_count
    if new_count > 0 and new_count <= credential.sign_count:
        raise InvalidRegistrationResponse("Passkey reuse detected — please try again.")

    credential.sign_count = new_count
    credential.last_used_at = timezone.now()
    credential.save(update_fields=["sign_count", "last_used_at"])
    cache.delete(_LOGIN_CHALLENGE_KEY.format(challenge_id=challenge_id))
    return credential
