from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import UserDetailsSerializer
from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


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
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined", "nid_verified"]


class CustomUserDetailsSerializer(UserDetailsSerializer):
    """Used by dj-rest-auth's GET/PUT /api/v1/auth/user/."""

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
        )
        read_only_fields = ("email", "nid_verified")


class CustomRegisterSerializer(RegisterSerializer):
    """Used by dj-rest-auth's POST /api/v1/auth/register/."""

    phone = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=User.Role.choices, required=False, default=User.Role.TENANT)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data["phone"] = self.validated_data.get("phone", "")
        data["role"] = self.validated_data.get("role", User.Role.TENANT)
        return data

    def save(self, request):
        user = super().save(request)
        user.phone = self.cleaned_data.get("phone", "")
        user.role = self.cleaned_data.get("role", User.Role.TENANT)
        user.save(update_fields=["phone", "role"])
        return user
