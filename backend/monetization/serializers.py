from rest_framework import serializers

from .models import Commission, Payout, RevenueLedgerEntry


class RevenueLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueLedgerEntry
        fields = [
            "id",
            "entry_type",
            "scope",
            "user",
            "gross_amount",
            "platform_amount",
            "partner_amount",
            "currency",
            "source_type",
            "source_id",
            "detail",
            "created_at",
        ]
        read_only_fields = fields


class CommissionSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.username", read_only=True)

    class Meta:
        model = Commission
        fields = [
            "id",
            "kind",
            "recipient",
            "recipient_name",
            "amount",
            "rate",
            "status",
            "source_type",
            "source_id",
            "detail",
            "created_at",
            "paid_at",
        ]
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.username", read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "recipient",
            "recipient_name",
            "amount",
            "method",
            "account_details",
            "status",
            "period_start",
            "period_end",
            "reference",
            "reason",
            "created_at",
            "decided_at",
        ]
        read_only_fields = fields
