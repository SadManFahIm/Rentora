from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Read/patch representation of a notification.

    Everything except ``is_read`` is read-only: notifications are authored
    server-side, and the only client mutation is marking one read/unread.
    """

    notification_type_display = serializers.CharField(
        source="get_notification_type_display", read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "is_read",
            "action_url",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "title",
            "message",
            "action_url",
            "created_at",
        ]
