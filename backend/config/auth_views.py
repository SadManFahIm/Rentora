"""Throttled auth endpoints.

dj-rest-auth ships its own ``LoginView`` / ``RegisterView``; we subclass them
purely to attach :class:`config.throttling.AuthRateThrottle` (10/hour per IP)
so credential-guessing and signup spam are rate-limited. Routed ahead of the
dj-rest-auth includes in ``config/urls.py`` so these override the defaults.

The login subclass also intercepts 2FA: when the authenticating account has
``otp_enabled``, instead of issuing JWTs it mints an email-OTP challenge and
returns ``202 Pending`` so the client can prompt for the one-time code.
"""

from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.views import LoginView
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from users.serializers import CustomUserDetailsSerializer
from users.services import _mask_email, create_challenge

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
    """dj-rest-auth login, throttled per IP, with email-OTP 2FA intercept."""

    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        # dj-rest-auth's serializer authenticates the user and validates the
        # password, raising 400 on bad credentials.
        self.request = request
        self.serializer = self.get_serializer(data=request.data)
        self.serializer.is_valid(raise_exception=True)
        user = self.serializer.validated_data["user"]

        if user.otp_enabled:
            challenge = create_challenge(user)
            return Response(
                {
                    "otp_required": True,
                    "challenge": challenge.challenge_token,
                    "destination_masked": _mask_email(user.email or ""),
                    "expires_in": int(getattr(settings, "OTP_TTL_SECONDS", 600)),
                    "user": CustomUserDetailsSerializer(user, context=request).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        return super().post(request, *args, **kwargs)


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
