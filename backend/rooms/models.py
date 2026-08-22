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
        # Core areas (Phase 1) + the wider Dhaka sprawl (Phase 11) — the
        # gazetteer in rooms/streets.py mirrors these so map search and the
        # natural-language parser recognise the same place names.
        DHANMONDI = "Dhanmondi", "Dhanmondi"
        MIRPUR = "Mirpur", "Mirpur"
        GULSHAN = "Gulshan", "Gulshan"
        BANANI = "Banani", "Banani"
        MOHAMMADPUR = "Mohammadpur", "Mohammadpur"
        AZIMPUR = "Azimpur", "Azimpur"
        UTTARA = "Uttara", "Uttara"
        TEJGAON = "Tejgaon", "Tejgaon"
        BADDA = "Badda", "Badda"
        RAMPURA = "Rampura", "Rampura"
        BANASREE = "Banasree", "Banasree"
        KHILGAON = "Khilgaon", "Khilgaon"
        MOTIJHEEL = "Motijheel", "Motijheel"
        OLD_DHAKA = "Old Dhaka", "Old Dhaka"
        BASHUNDHARA = "Bashundhara", "Bashundhara"
        LALMATIA = "Lalmatia", "Lalmatia"
        SHYAMOLI = "Shyamoli", "Shyamoli"
        SAVAR = "Savar", "Savar"
        KERANIGANJ = "Keraniganj", "Keraniganj"
        TONGI = "Tongi", "Tongi"

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
    # Phase 17 — Photo-Geo Authenticity (Stage 5): GPS extracted from EXIF
    # at upload time (before strip_exif runs). Compared against the room's
    # declared lat/lng to detect stock-photo or stolen-image fraud.
    photo_lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude extracted from photo EXIF data.",
    )
    photo_lng = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude extracted from photo EXIF data.",
    )
    photo_gps_accuracy = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="GPS accuracy: high (with GPS method), medium (GPS data present), or empty.",
    )

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Image for {self.room.title}"


class RoomPriceHistory(models.Model):
    """Every price change of a listing (Phase 11+ — price-drop intelligence).

    One row per observed price, written by a post-save signal only when the
    price actually changed, so ``latest two rows = the most recent change``.
    Powers saved-search "price dropped by X%" alerts and landlord price
    history without a heavier audit trail.
    """

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="price_history")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["room", "changed_at"], name="room_price_hist_idx")]

    def __str__(self) -> str:
        return f"{self.room.title}: ৳{self.price} @ {self.changed_at:%Y-%m-%d}"


class RoomImageHash(models.Model):
    """Perceptual-hash cache for image similarity search (Phase 11).

    Computing an average hash over every room photo on every request is
    wasteful, so each primary image's 64-bit hash is computed once and cached
    here, keyed by the source file's mtime — when the file changes the hash is
    recomputed. ``image_updated_at`` mirrors the file mtime at hash time.
    """

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="image_hashes")
    image = models.ForeignKey(RoomImage, on_delete=models.CASCADE, related_name="hash_entries")
    phash_hex = models.CharField(max_length=16)  # 64-bit average hash, hex
    image_updated_at = models.DateTimeField()  # source file mtime at hash time
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["phash_hex"], name="room_img_hash_idx")]

    def __str__(self) -> str:
        return f"hash {self.phash_hex} for {self.room.title}"


class RoomVisionAnalysis(models.Model):
    """Stored vision analysis of a listing's photos (Phase 14 — AI v3).

    The deterministic photo pipeline (lighting / tones / décor / framing
    observations + caption + palette) is cached here so the dashboard panel
    renders instantly and re-analysis is explicit. ``suggested_amenities``
    are never applied automatically — the landlord reviews them.
    """

    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="vision_analysis")
    provider = models.CharField(max_length=16, default="heuristic")
    caption = models.TextField(blank=True, default="")
    observations = models.JSONField(default=list)
    suggested_amenities = models.JSONField(default=list)
    palette = models.JSONField(default=list)
    photo_profiles = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"vision ({self.provider}) for {self.room.title}"
