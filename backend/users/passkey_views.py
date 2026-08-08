"""WebAuthn / FIDO2 passkey endpoints.

Registration (JWT-authenticated)::

    POST /api/v1/auth/passkey/register/begin/    → options payload
    POST /api/v1/auth/passkey/register/complete/ → store the new credential

Authentication (passwordless, public)::

    POST /api/v1/auth/passkey/login/begin/       → options + challenge_id
    POST /api/v1/auth/passkey/login/complete/    → verified → JWT tokens

The passkey is a first-class login method: completing authentication issues
the same JWTs as password login (2FA accounts still get the OTP step).
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttling import AuthRateThrottle

from . import passkey as passkey_service
from .otp_views import _issue_tokens, pending_otp_response
from .serializers import PasskeySerializer


class PasskeyRegisterBeginView(APIView):
    """Generate registration options for the authenticated user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        options = passkey_service.generate_registration_options(request.user)
        return Response(options, status=status.HTTP_200_OK)


class PasskeyRegisterCompleteView(APIView):
    """Verify the authenticator's response and store the passkey."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PasskeySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = passkey_service.verify_registration_response(
                request.user,
                ser.validated_data["response"],
                name=ser.validated_data.get("name", ""),
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc),
                    "errors": ["passkey_registration_failed"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"success": True, **result},
            status=status.HTTP_201_CREATED,
        )


class PasskeyLoginBeginView(APIView):
    """Generate authentication options for a discoverable-credential flow.

    ``allow_credentials`` is intentionally empty so the browser can offer any
    passkey registered to this RP (conditional UI on the login form).
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        options = passkey_service.generate_authentication_options()
        return Response(options, status=status.HTTP_200_OK)


class PasskeyLoginCompleteView(APIView):
    """Verify the assertion and issue JWTs for the passkey's owner."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ser = PasskeySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            credential = passkey_service.verify_authentication_response(
                ser.validated_data.get("challenge_id", ""),
                ser.validated_data["response"],
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc),
                    "errors": ["passkey_authentication_failed"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = credential.user
        if not user.is_active:
            return Response(
                {
                    "success": False,
                    "message": "This account is no longer active.",
                    "errors": ["inactive_account"],
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        # 2FA users still prove the emailed code after the passkey — identical
        # behaviour to the password login intercept.
        if user.otp_enabled:
            return pending_otp_response(request, user)
        return Response(_issue_tokens(request, user), status=status.HTTP_200_OK)
