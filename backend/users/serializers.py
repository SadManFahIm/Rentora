from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class DuplicateEmailError(serializers.ValidationError):
    """Raised when registration attempts to reuse an existing account's email.

    Subclassing ValidationError keeps the envelope shape consistent — the
    custom exception handler turns it into a 400 with a readable message.
    """


class UserSerializer(serializers.ModelSerializer):
    """General-purpose user representation, used by UserViewSet."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "role",
            "gender",
            "nid_verified",
            "bio",
            "date_of_birth",
            "otp_enabled",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined", "nid_verified"]


class CustomUserDetailsSerializer(UserDetailsSerializer):
    """Used by dj-rest-auth's GET/PUT /api/v1/auth/user/."""

    passkeys = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "pk",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "role",
            "gender",
            "nid_verified",
            "bio",
            "date_of_birth",
            "otp_enabled",
            "passkeys",
        )
        read_only_fields = ("email", "nid_verified")

    def get_passkeys(self, obj):
        return [
            {
                "id": cred.credential_id,
                "name": cred.name or "Passkey",
                "created_at": cred.created_at.isoformat(),
                "last_used_at": cred.last_used_at.isoformat() if cred.last_used_at else None,
            }
            for cred in obj.passkeys.all()[:10]
        ]


class CustomRegisterSerializer(RegisterSerializer):
    """Used by dj-rest-auth's POST /api/v1/auth/register/.

    Extends the default registration with a display ``name`` (stored on
    ``first_name``) plus ``phone`` and ``role``. ``username`` remains required
    by allauth; the frontend supplies the email as the username.
    """

    name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=User.Role.choices, required=False, default=User.Role.TENANT
    )

    def validate_email(self, email):
        # dj-rest-auth's default check only consults allauth's EmailAddress
        # table, so accounts created outside the signup flow (admin,
        # createsuperuser, seed scripts, shell) slipped through and a
        # duplicate email could be registered. Enforce uniqueness against
        # the user table itself as well.
        email = super().validate_email(email)
        if (
            email
            and User.objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        ):
            raise DuplicateEmailError(
                {"email": "A user is already registered with this email address."}
            )
        return email

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data["name"] = self.validated_data.get("name", "")
        data["phone"] = self.validated_data.get("phone", "")
        data["role"] = self.validated_data.get("role", User.Role.TENANT)
        return data

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data.get("name", "")
        user.phone = self.cleaned_data.get("phone", "")
        user.role = self.cleaned_data.get("role", User.Role.TENANT)
        user.save(update_fields=["first_name", "phone", "role"])
        return user


# ============================================================
# Email-OTP two-factor authentication
# ============================================================


class OTPSerializer(serializers.Serializer):
    """Shared input for the verify/resend/toggle-OTP endpoints."""

    challenge = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField(required=False, allow_blank=True, max_length=10)
    recovery_code = serializers.CharField(
        required=False, allow_blank=True, max_length=16, label="Recovery code"
    )
    password = serializers.CharField(
        required=False, allow_blank=True, write_only=True, style={"input_type": "password"}
    )
    enable = serializers.BooleanField(required=False, default=True)


class PasskeySerializer(serializers.Serializer):
    """Input for passkey registration/authentication completions."""

    response = serializers.JSONField()
    challenge_id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)
