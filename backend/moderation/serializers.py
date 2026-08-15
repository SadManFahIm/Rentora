from rest_framework import serializers

from .models import PhotoModeration, ReviewModeration

# How much of a review comment admins see in the queue. Comments are
# user-generated content an admin must judge, so a truncated preview is
# appropriate — but never the full body when it is long enough to be an
# email/dossier dump.
COMMENT_PREVIEW_CHARS = 300


class ReviewModerationSerializer(serializers.ModelSerializer):
    """One review in the moderation queue (admin view)."""

    room_id = serializers.IntegerField(source="review.room_id", read_only=True)
    room_title = serializers.CharField(source="review.room.title", read_only=True)
    author_username = serializers.CharField(source="review.user.username", read_only=True)
    author_name = serializers.SerializerMethodField()
    rating = serializers.IntegerField(source="review.rating", read_only=True)
    comment_preview = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=""
    )

    class Meta:
        model = ReviewModeration
        fields = [
            "id",
            "review",
            "room_id",
            "room_title",
            "author_username",
            "author_name",
            "rating",
            "comment_preview",
            "status",
            "status_display",
            "risk_score",
            "signals",
            "admin_note",
            "reviewed_by_username",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields

    def get_author_name(self, obj: ReviewModeration) -> str:
        return obj.review.user.get_full_name() or obj.review.user.username

    def get_comment_preview(self, obj: ReviewModeration) -> str:
        text = obj.review.comment or ""
        return text[:COMMENT_PREVIEW_CHARS] + ("…" if len(text) > COMMENT_PREVIEW_CHARS else "")


class PhotoModerationSerializer(serializers.ModelSerializer):
    """One photo in the moderation queue (admin view)."""

    target_type_display = serializers.CharField(source="get_target_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    room_title = serializers.CharField(source="room.title", read_only=True, default="")
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True, default=""
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, default=""
    )

    class Meta:
        model = PhotoModeration
        fields = [
            "id",
            "target_type",
            "target_type_display",
            "room",
            "room_title",
            "review",
            "image_url",
            "phash",
            "status",
            "status_display",
            "risk_score",
            "signals",
            "admin_note",
            "uploaded_by_username",
            "reviewed_by_username",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields
