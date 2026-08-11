from django.conf import settings
from django.db import models


class Room(models.Model):
    class RoomType(models.TextChoices):
        SINGLE = "single", "Single"
        SHARED = "shared", "Shared"
        STUDIO = "studio", "Studio"

    class Tier(models.TextChoices):
        """Paid listing tiers (monetization). Free is the default; Featured and
        Premium are unlocked through a paid promotion and expire after
        LISTING_TIER_DURATION_DAYS (see config/settings/base.py).
        """

        FREE = "free", "Free"
        FEATURED = "featured", "Featured"
        PREMIUM = "premium", "Premium"

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
    gender_preference = models.CharField(
        max_length=10, choices=GenderPreference.choices, default=GenderPreference.ANY
    )
    size_sqft = models.IntegerField()
    is_available = models.BooleanField(default=True)
    # Paid-listing tier (monetization). `is_featured` below stays in sync
    # (True once tier is featured/premium) so existing "featured rooms"
    # surfaces keep working; `tier` is the source of truth going forward.
    tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.FREE)
    tier_expires_at = models.DateTimeField(null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rooms"
    )
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_reviews = models.IntegerField(default=0)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        # The map view filters by a viewport box (lat/lng ranges) and radius
        # queries do an indexable bbox pre-filter, so a composite index over
        # lat/lng keeps those queries fast as the listing count grows —
        # without PostGIS, this is the main lever for geo query speed.
        indexes = [models.Index(fields=["lat", "lng"], name="room_lat_lng_idx")]

    def __str__(self):
        return self.title


class RoomView(models.Model):
    """One detail-page view of a room (Phase 10 — landlord insights).

    Logged for every room detail GET, deduplicated per (viewer, room) inside
    a short window so a refresh doesn't inflate the count. Anonymous viewers
    aren't tracked (we don't cookie users), so counts are a lower bound on
    real traffic — still the right signal for landlords comparing listings.
    """

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="views")
    viewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at"]
        indexes = [
            models.Index(fields=["room", "viewed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.viewer or 'anon'} viewed {self.room.title}"


class RoomImage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="rooms/")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Image for {self.room.title}"
