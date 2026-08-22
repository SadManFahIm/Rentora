from rest_framework import serializers

from .models import CorporateAccount, CorporateInvoice, CorporateMember


class CorporateAccountSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = CorporateAccount
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "vat_number",
            "owner",
            "owner_name",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "owner", "owner_name", "status", "created_at"]


class CorporateMemberSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CorporateMember
        fields = ["id", "account", "user", "user_name", "email", "role", "created_at"]
        read_only_fields = ["id", "account", "user", "user_name", "email", "created_at"]


class CorporateInvoiceSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = CorporateInvoice
        fields = [
            "id",
            "account",
            "account_name",
            "invoice_number",
            "period_start",
            "period_end",
            "amount",
            "status",
            "line_items",
            "created_at",
        ]
        read_only_fields = fields
