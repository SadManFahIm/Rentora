"""Phone (SMS) OTP login endpoints (Phase 13 — reach).

Passwordless sign-in for Bangladesh's mobile-first audience: request a
6-digit code for a Bangladeshi mobile number, then exchange ``(phone, code)``
for JWTs. A phone that hasn't registered yet is created on the first
successful verification, so the SMS path never blocks a new tenant behind an
email address.

- ``POST /api/v1/auth/sms/request/`` — send a 6-digit code (cooldown-guarded)
- ``POST /api/v1/auth/sms/verify/`` — exchange (phone, code) → JWT tokens

Both are gated by ``SMS_OTP_ENABLED`` (OFF by default — a deployment turns it
on only when an SMS gateway is configured) and throttled per-IP like every
other auth endpoint.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from config.throttling import AuthRateThrottle

from .serializers import (
    CustomUserDetailsSerializer,
    SmsOtpRequestSerializer,
    SmsOtpVerifySerializer,
)
from .sms import sms_otp_enabled
from .sms_services import CooldownError, create_sms_challenge, verify_sms_code

User = get_user_model()


def _issue_tokens(request, user) -> dict:
    """Same JWT response shape as the rest of auth (dj-rest-auth compatible)."""
    refresh_token = RefreshToken.for_user(user)
    return {
        "user": CustomUserDetailsSerializer(user, context=request).data,
        "access": str(refresh_token.access_token),
        "refresh": str(refresh_token),
        "access_expiration": int(refresh_token.access_token.payload["exp"]),
        "refresh_expiration": int(refresh_token.payload["exp"]),
    }


def _sms_disabled() -> Response:
    return Response(
        {
            "success": False,
            "message": "Phone sign-in is not enabled on this deployment.",
            "errors": ["sms_disabled"],
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _get_or_create_user(phone: str):
    """The user for ``phone``, created on first successful verification.

    A phone number is the identity here, so the username derives from it
    (stable and unique); the role defaults to tenant and the account has no
    password — the user can still add email/password from the dashboard.
    """
    user = User.objects.filter(phone=phone).first()
    if user is not None:
        return user

    base = f"bd{phone[-10:]}"
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():  # pragma: no cover
        counter += 1
        username = f"{base}{counter}"
    return User.objects.create(username=username, phone=phone, role=User.Role.TENANT)


class SmsOtpRequestView(APIView):
    """Send a 6-digit code by SMS to a Bangladeshi mobile number."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = SmsOtpRequestSerializer

    def post(self, request):
        if not sms_otp_enabled():
            return _sms_disabled()

        serializer = SmsOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        try:
            _, masked, ttl = create_sms_challenge(phone)
        except CooldownError as exc:
            return Response(
                {
                    "success": False,
                    "message": f"Please wait {exc.remaining}s before requesting another code.",
                    "errors": ["resend_blocked"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "phone_masked": masked,
                "expires_in": ttl,
                "message": "We sent a 6-digit code by SMS. It expires in 10 minutes.",
            },
            status=status.HTTP_200_OK,
        )


class SmsOtpVerifyView(APIView):
    """Exchange (phone, code) for JWTs — logging in or auto-registering."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = SmsOtpVerifySerializer

    def post(self, request):
        if not sms_otp_enabled():
            return _sms_disabled()

        serializer = SmsOtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]

        ok, message = verify_sms_code(phone, code)
        if not ok:
            return Response(
                {"success": False, "message": message, "errors": ["invalid_code"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = _get_or_create_user(phone)
        return Response(_issue_tokens(request, user), status=status.HTTP_200_OK)
