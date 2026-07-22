"""Throttled auth endpoints.

dj-rest-auth ships its own ``LoginView`` / ``RegisterView``; we subclass them
purely to attach :class:`config.throttling.AuthRateThrottle` (10/hour per IP)
so credential-guessing and signup spam are rate-limited. Routed ahead of the
dj-rest-auth includes in ``config/urls.py`` so these override the defaults.
"""

from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import LoginView
from drf_spectacular.utils import extend_schema

from .throttling import AuthRateThrottle


@extend_schema(
    tags=["Auth"],
    summary="Obtain JWT tokens",
    description=(
        "Authenticate with email/username + password and receive access and "
        "refresh JWTs. Rate limited to 10 requests/hour per IP address."
    ),
)
class ThrottledLoginView(LoginView):
    """dj-rest-auth login, throttled per IP."""

    throttle_classes = [AuthRateThrottle]


@extend_schema(
    tags=["Auth"],
    summary="Register a new account",
    description=(
        "Create a tenant or landlord account. Returns the new user and JWTs. "
        "Rate limited to 10 requests/hour per IP address."
    ),
)
class ThrottledRegisterView(RegisterView):
    """dj-rest-auth registration, throttled per IP."""

    throttle_classes = [AuthRateThrottle]
