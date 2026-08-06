from django.conf import settings
from django.db import models


class Room(models.Model):
    class RoomType(models.TextChoices):
        SINGLE = "single", "Single"
        SHARED = "shared", "Shared"
        STUDIO = "studio", "Studio"

    class GenderPreference(models.TextChoices):
        ANY = "any", "Any"
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    class Area(models.TextChoices):
        DHANMONDI = "Dhanmondi", "Dhanmondi"
        MIRPUR = "Mirpur", "Mirpur"
        GULSHAN = "Gulshan", "Gulshan"
        BANANI = "Banani", "Banani"
        MOHAMMADPUR = "Mohammadpur", "Mohammadpur"
        AZIMPUR = "Azimpur", "Azimpur"

    title = models.CharField(max_length=200)
    description = models.TextField()
    room_type = models.CharField(max_length=10, choices=RoomType.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    area = models.CharField(max_length=50, choices=Area.choices)
    address = models.TextField()
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    amenities = models.JSONField(default=list)
    gender_preference = models.CharField(max_length=10, choices=GenderPreference.choices, default=GenderPreference.ANY)
    size_sqft = models.IntegerField()
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rooms")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_reviews = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class RoomImage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="rooms/")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Image for {self.room.title}"
