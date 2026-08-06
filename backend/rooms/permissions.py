from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Read access for everyone; write access only for the room's owner."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner_id == request.user.id
