import django_filters
from rest_framework import permissions, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import Room
from .permissions import IsOwnerOrReadOnly
from .serializers import RoomCreateUpdateSerializer, RoomDetailSerializer, RoomListSerializer


class RoomFilter(django_filters.FilterSet):
    price__gte = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = Room
        fields = ["area", "room_type", "gender_preference", "is_available", "is_featured"]


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.select_related("owner").prefetch_related("images").all()
    filterset_class = RoomFilter
    filter_backends = [django_filters.rest_framework.DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["title", "description", "area"]
    ordering_fields = ["price", "rating", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return RoomListSerializer
        if self.action == "retrieve":
            return RoomDetailSerializer
        return RoomCreateUpdateSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
