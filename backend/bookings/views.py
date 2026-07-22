from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from .models import Booking, Review
from .permissions import IsReviewAuthorOrReadOnly, IsTenantOrRoomOwner
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    BookingUpdateSerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)


class BookingViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        user = self.request.user
        return (
            Booking.objects.select_related("room", "room__owner", "tenant")
            .filter(Q(tenant=user) | Q(room__owner=user))
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        if self.action in ("update", "partial_update"):
            return BookingUpdateSerializer
        return BookingSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "retrieve"):
            return [permissions.IsAuthenticated(), IsTenantOrRoomOwner()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        output = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        output = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(output.data)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related("user", "room").all()
    filterset_fields = ["room"]

    def get_serializer_class(self):
        if self.action == "create":
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsReviewAuthorOrReadOnly()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        output = ReviewSerializer(review, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)
