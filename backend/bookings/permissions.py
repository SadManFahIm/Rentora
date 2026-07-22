from rest_framework import permissions


class IsTenantOrRoomOwner(permissions.BasePermission):
    """A booking is visible/actionable by the tenant who made it or the room's owner."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        return obj.tenant_id == user.id or obj.room.owner_id == user.id


class IsReviewAuthorOrReadOnly(permissions.BasePermission):
    """Read access for everyone; write access only for the review's author."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user_id == request.user.id
