from rest_framework import serializers

from .models import SavedSearch


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = ["id", "name", "filters", "last_checked_at", "created_at"]
        read_only_fields = ["id", "last_checked_at", "created_at"]
