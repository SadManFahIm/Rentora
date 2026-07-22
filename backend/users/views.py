from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import User
from .serializers import UserSerializer


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only user directory. Staff see everyone; regular users see only themselves."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return User.objects.all().order_by("id")
        return User.objects.filter(pk=user.pk)
