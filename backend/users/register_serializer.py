"""Registration serializer for the referral program.

Extends the project's ``CustomRegisterSerializer`` (which already validates
duplicate emails against the user table and stores name/phone/role) with an
optional ``ref`` code so signups can be attributed to whoever invited them.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .serializers import CustomRegisterSerializer

User = get_user_model()


class RentoraRegisterSerializer(CustomRegisterSerializer):
    """CustomRegisterSerializer that also links the account to a referrer."""

    ref = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=16)

    def save(self, request):
        user = super().save(request)
        ref_code = (self.validated_data.get("ref") or "").strip().upper()
        if ref_code and ref_code != user.referral_code:
            referrer = User.objects.filter(referral_code=ref_code).exclude(pk=user.pk).first()
            if referrer is not None:
                user.referred_by = referrer
                user.save(update_fields=["referred_by"])
        return user
