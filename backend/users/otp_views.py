"""Email-OTP two-factor authentication endpoints.

Complement the login flow (which returns a pending OTP challenge for
2FA-enabled accounts — see ``config/auth_views.ThrottledLoginView``):

- ``POST /api/v1/auth/otp/verify/``   — exchange (challenge, code) → JWTs
- ``POST /api/v1/auth/otp/resend/``   — re-issue the code for a challenge
- ``POST /api/v1/auth/otp/toggle/``   — enable/disable 2FA for my account
                                        (requires the current password)
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from config.throttling import AuthRateThrottle

from .models import OTPChallenge
from .serializers import CustomUserDetailsSerializer, OTPSerializer
from .services import _sha256, resend_code, verify_code

User = get_user_model()


def _issue_tokens(request, user) -> dict:
    """Return the JWT response body for a successfully authenticated user.

    Matches the dj-rest-auth login shape (``REST_AUTH.JWT_AUTH_RETURN_EXPIRATION``
    is on, so the expirations are included as unix timestamps)."""
    refresh_token = RefreshToken.for_user(user)
    return {
        "user": CustomUserDetailsSerializer(user, context=request).data,
        "access": str(refresh_token.access_token),
        "refresh": str(refresh_token),
        "access_expiration": int(refresh_token.access_token.payload["exp"]),
        "refresh_expiration": int(refresh_token.payload["exp"]),
    }


class OTPVerifyView(APIView):
    """Exchange the emailed 6-digit code for JWT tokens."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = OTPSerializer

    def post(self, request):
        ser = OTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        challenge = self._get_challenge(ser.validated_data.get("challenge", ""))
        if challenge is None:
            return Response(
                {
                    "success": False,
                    "message": "This sign-in session is no longer valid. Please sign in again.",
                    "errors": ["invalid_challenge"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, message = verify_code(challenge, ser.validated_data.get("code", ""))
        if not ok:
            return Response(
                {
                    "success": False,
                    "message": message,
                    "errors": ["invalid_code"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The user has proven possession of the email + the password (login
        # already checked it); hand them the same JWTs login would have.
        return Response(_issue_tokens(request, challenge.user), status=status.HTTP_200_OK)

    @staticmethod
    def _get_challenge(challenge_token: str) -> OTPChallenge | None:
        if not challenge_token:
            return None
        # Matched by token only; verify_code enforces the status lifecycle
        # (pending/used/expired/locked) so a locked challenge reports the
        # lock reason instead of silently turning into "invalid session".
        return OTPChallenge.objects.filter(challenge_token_hash=_sha256(challenge_token)).first()


class OTPResendView(APIView):
    """Re-send the code for a pending challenge (cooldown-guarded)."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]
    serializer_class = OTPSerializer

    def post(self, request):
        ser = OTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        challenge = OTPVerifyView._get_challenge(ser.validated_data.get("challenge", ""))
        if challenge is None:
            return Response(
                {
                    "success": False,
                    "message": "This sign-in session is no longer valid. Please sign in again.",
                    "errors": ["invalid_challenge"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        ok, message = resend_code(challenge)
        if not ok:
            return Response(
                {
                    "success": False,
                    "message": message,
                    "errors": ["resend_blocked"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"success": True, "message": "A new code has been sent."},
            status=status.HTTP_200_OK,
        )


class OTPToggleView(APIView):
    """Enable/disable email-OTP 2FA on the caller's own account.

    Enabling requires the current password (protects against a session
    hijacker silently forcing 2FA on to lock the real owner out).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OTPSerializer

    def post(self, request):
        ser = OTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enable = bool(ser.validated_data.get("enable", True))

        if enable:
            password = ser.validated_data.get("password", "")
            if not request.user.check_password(password):
                return Response(
                    {
                        "success": False,
                        "message": "Your current password is incorrect.",
                        "errors": ["wrong_password"],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not request.user.email:
                return Response(
                    {
                        "success": False,
                        "message": "Add an email address to your account before enabling 2FA.",
                        "errors": ["no_email"],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            request.user.otp_enabled = True
        else:
            request.user.otp_enabled = False
        request.user.save(update_fields=["otp_enabled"])

        return Response(
            {
                "success": True,
                "otp_enabled": request.user.otp_enabled,
                "message": "Two-factor authentication is now "
                + ("enabled." if enable else "disabled."),
            },
            status=status.HTTP_200_OK,
        )
