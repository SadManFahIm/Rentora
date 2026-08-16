from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from .models import KycDocument, TenantVerification

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
            "tenant_verified",
            "bio",
            "date_of_birth",
            "otp_enabled",
            "digest_emails_enabled",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined", "nid_verified", "tenant_verified"]


class CustomUserDetailsSerializer(UserDetailsSerializer):
    """Used by dj-rest-auth's GET/PUT /api/v1/auth/user/."""

    passkeys = serializers.SerializerMethodField()
    # Tier 3: transparent behavioral trust signals (completed bookings etc.)
    trust_signals = serializers.SerializerMethodField()

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
            "is_staff",
            "gender",
            "nid_verified",
            "tenant_verified",
            "bio",
            "date_of_birth",
            "otp_enabled",
            "digest_emails_enabled",
            "passkeys",
            "trust_signals",
        )
        read_only_fields = ("email", "nid_verified", "tenant_verified")

    @extend_schema_field(
        inline_serializer(
            "TrustSignals",
            fields={
                "tenant_verified": serializers.BooleanField(read_only=True),
                "nid_verified": serializers.BooleanField(read_only=True),
                "completed_bookings": serializers.IntegerField(read_only=True),
                "profile_complete": serializers.BooleanField(read_only=True),
            },
        )
    )
    def get_trust_signals(self, obj):
        from .trust import trust_signals

        return trust_signals(obj)

    @extend_schema_field(
        serializers.ListField(
            child=inline_serializer(
                "PasskeyItem",
                fields={
                    "id": serializers.CharField(read_only=True),
                    "name": serializers.CharField(read_only=True),
                    "created_at": serializers.CharField(read_only=True),
                    "last_used_at": serializers.CharField(
                        read_only=True, allow_null=True, required=False
                    ),
                },
            )
        )
    )
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


# ============================================================
# KYC verification (documents + admin review panel)
# ============================================================


class KycUploadRequestSerializer(serializers.Serializer):
    """Multipart request body for a document upload (schema documentation;
    the view validates against the actual file object)."""

    doc_type = serializers.ChoiceField(choices=KycDocument.DocType.choices)
    file = serializers.FileField()


class KycDocumentSerializer(serializers.ModelSerializer):
    """One submitted KYC document.

    Only the owner and staff/admins ever receive this serializer (the views
    enforce it), and the ``file`` field points at the *authenticated* file
    endpoint rather than the public MEDIA_URL — so the bytes stay private
    even though Django's dev server serves /media/ to anyone.
    """

    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    file = serializers.SerializerMethodField()

    class Meta:
        model = KycDocument
        fields = [
            "id",
            "doc_type",
            "doc_type_display",
            "file",
            "status",
            "status_display",
            "review_note",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields

    def get_file(self, obj: KycDocument) -> str:
        """The permission-gated file URL (owner/admin only)."""
        path = reverse("kyc-document-file", args=[obj.pk])
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class KycPendingUserSerializer(serializers.ModelSerializer):
    """One applicant in the admin review panel: profile summary + documents."""

    name = serializers.SerializerMethodField()
    # ``source`` is the model related_name (``kyc_documents``); the API field
    # stays ``documents`` for readability.
    documents = KycDocumentSerializer(many=True, read_only=True, source="kyc_documents")

    class Meta:
        model = User
        fields = ["id", "username", "email", "name", "phone", "role", "nid_verified", "documents"]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username


class KycReviewRequestSerializer(serializers.Serializer):
    """Admin decision on a user's KYC application."""

    approved = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class KycSlaSerializer(serializers.Serializer):
    """Admin review-queue health: how many applications are waiting, how fast
    decisions happen, and whether that pace is improving or slipping.

    All durations are in hours. ``decision_delta_7d`` is this week's decision
    count minus last week's, so a negative value means the queue is growing.
    """

    pending_count = serializers.IntegerField()
    resolved_count = serializers.IntegerField()
    avg_review_hours = serializers.FloatField(allow_null=True)
    last_7d_decisions = serializers.IntegerField()
    last_7d_avg_review_hours = serializers.FloatField(allow_null=True)
    prev_7d_decisions = serializers.IntegerField()
    decision_delta_7d = serializers.IntegerField()
    pending_oldest_hours = serializers.FloatField(allow_null=True)
    # Breach flags — which review SLA is currently being missed.
    breaches = serializers.ListField(child=serializers.CharField())
    # Last 30 days, oldest first: decisions per day + average review hours.
    trend_30d = serializers.ListField(child=serializers.DictField())


class KycAuditEntrySerializer(serializers.Serializer):
    """One KYC decision from the append-only audit log, shaped for the admin
    panel's history view (who decided, on whom, when, with what note)."""

    id = serializers.IntegerField()
    action = serializers.CharField()
    actor_username = serializers.CharField()
    actor_name = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    user_name = serializers.CharField()
    note = serializers.CharField(default="")
    created_at = serializers.DateTimeField()


# ============================================================
# Tenant KYC verification (Phase 12 — two-sided trust)
# ============================================================


class TenantVerificationSerializer(serializers.ModelSerializer):
    """The tenant's own verification record.

    Only ever returned to the tenant themselves or to staff/admins (the views
    enforce it). The ``file`` field points at the *authenticated* file
    endpoint rather than the public MEDIA_URL, and is only populated for the
    owner and admins — everyone else simply never receives this serializer.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)
    file = serializers.SerializerMethodField()

    class Meta:
        model = TenantVerification
        fields = [
            "id",
            "status",
            "status_display",
            "doc_type",
            "doc_type_display",
            "file",
            "review_note",
            "created_at",
            "updated_at",
            "reviewed_at",
            "expires_at",
            "auto_screen_score",
            "auto_screen_result",
            "auto_screen_detail",
        ]
        read_only_fields = fields

    def get_file(self, obj: TenantVerification) -> str | None:
        """The permission-gated file URL (owner/admin only) — never MEDIA_URL."""
        if not obj.file:
            return None
        path = reverse("tenant-kyc-file", args=[obj.user_id])
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class TenantKycReviewRequestSerializer(serializers.Serializer):
    """Admin decision on a tenant's verification.

    ``decision`` is one of approved | rejected | needs_review; ``note`` is the
    reviewer's reason (required for rejected/needs_review so the tenant knows
    what to fix, optional for approval).
    """

    decision = serializers.ChoiceField(choices=["approved", "rejected", "needs_review"])
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["decision"] in ("rejected", "needs_review") and not attrs.get("note", "").strip():
            raise serializers.ValidationError(
                {
                    "note": "A note explaining the decision is required for rejection or needs-review."
                }
            )
        return attrs


class TenantKycPendingSerializer(serializers.ModelSerializer):
    """One applicant in the admin tenant-verification queue: profile summary +
    their verification record (with the admin-gated document URL)."""

    name = serializers.SerializerMethodField()
    verification = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "name",
            "phone",
            "role",
            "tenant_verified",
            "verification",
        ]

    def get_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_verification(self, obj):
        verification = getattr(obj, "tenant_verification", None)
        if verification is None:
            return None
        return TenantVerificationSerializer(verification, context=self.context).data


class PasskeySerializer(serializers.Serializer):
    """Input for passkey registration/authentication completions."""

    response = serializers.JSONField()
    challenge_id = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)
