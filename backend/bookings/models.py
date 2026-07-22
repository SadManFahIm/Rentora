from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from rooms.models import Room


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="bookings")
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    check_in = models.DateField()
    check_out = models.DateField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    agreement_signed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tenant} -> {self.room} ({self.status})"


class Review(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    verified_stay = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["room", "user"], name="unique_review_per_user_per_room"),
        ]

    def __str__(self):
        return f"{self.user} on {self.room} ({self.rating}*)"


def _recalculate_room_rating(room):
    agg = room.reviews.aggregate(avg=Avg("rating"), count=Count("id"))
    room.rating = agg["avg"] or 0
    room.total_reviews = agg["count"] or 0
    room.save(update_fields=["rating", "total_reviews"])


@receiver(post_save, sender=Review)
def update_room_rating_on_review_save(sender, instance, **kwargs):
    _recalculate_room_rating(instance.room)


@receiver(post_delete, sender=Review)
def update_room_rating_on_review_delete(sender, instance, **kwargs):
    _recalculate_room_rating(instance.room)
