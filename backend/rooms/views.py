from typing import Any

import django_filters
from django.conf import settings
from django.db import models
from django.db.models import Case, IntegerField, Q, Value, When
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from wishlist.models import Wishlist

from .geo import (
    BoundingBox,
    haversine_km,
    lat_delta_for_km,
    lng_delta_for_km,
)
from .geocoder import nominatim_search
from .image_search import similar_rooms
from .landmarks import ALL_LANDMARKS, get_landmark
from .map_intel import (
    affordability_stats,
    area_statistics,
    commute_eta,
    ideal_areas,
    map_search_rooms,
    nearest_metro_km,
    parse_map_query,
    value_score,
)
from .models import Room, RoomView
from .nl_query import parse_nl_query
from .permissions import IsOwnerOrReadOnly
from .ranking import hybrid_rank
from .semantic import semantic_candidates
from .serializers import (
    LandmarkSerializer,
    RoomCreateUpdateSerializer,
    RoomDetailSerializer,
    RoomListSerializer,
)
from .streets import area_center, search_streets


class RoomFilter(django_filters.FilterSet):
    price__gte = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    # Lets the landlord dashboard list only one owner's listings server-side
    # instead of pulling every page of all rooms and filtering client-side.
    owner = django_filters.NumberFilter(field_name="owner_id")
    # "Verified only" toggle on the rooms page — filters to listings whose
    # owner passed KYC (Room.verified, synced by users/signals.py).
    verified = django_filters.BooleanFilter(field_name="verified")

    class Meta:
        model = Room
        fields = ["area", "room_type", "gender_preference", "is_available", "is_featured"]


# Query params that the geo layer consumes directly in `get_queryset`, rather
# than through `RoomFilter` — declared here only so they show up in the
# OpenAPI schema for the list endpoint.
_GEO_PARAMS = [
    OpenApiParameter(
        "bbox",
        str,
        description="Map viewport filter, GeoJSON order: `minLng,minLat,maxLng,maxLat`. "
        "Returns only rooms inside the box.",
    ),
    OpenApiParameter(
        "near_lat", float, description="Reference-point latitude (pair with near_lng)."
    ),
    OpenApiParameter(
        "near_lng", float, description="Reference-point longitude (pair with near_lat)."
    ),
    OpenApiParameter(
        "near_landmark",
        str,
        description="Landmark slug (e.g. `du`, `mrt_mirpur_10`) used as the reference point "
        "instead of near_lat/near_lng. See the /rooms/landmarks/ endpoint for valid slugs.",
    ),
    OpenApiParameter(
        "radius_km",
        float,
        description="With a reference point, keep only rooms within this many km of it.",
    ),
]


@extend_schema_view(
    list=extend_schema(
        tags=["Rooms"],
        summary="List rooms",
        description=(
            "Public, paginated room listing. Supports filtering by "
            "`area`, `room_type`, `gender_preference`, `is_available`, "
            "`is_featured`, and a `price__gte`/`price__lte` range; full-text "
            "`search` over title/description/area; and `ordering` by price, "
            "rating or created_at.\n\n"
            "**Smart search (`smart=1`):** combines keyword + semantic ranking "
            "(vector space over title/area/description/address/amenities) with "
            'natural-language parsing — "১০ হাজার এর মধ্যে uttara room" is '
            "understood as budget ≤ ৳10,000 in Uttara. The response then "
            "carries an `nl_parsed` object describing what was understood.\n\n"
            "**Geo/map queries:** `bbox` filters to a map viewport; a reference "
            "point (`near_lat`+`near_lng`, or `near_landmark`) with `radius_km` "
            "filters to rooms near a place, and — unless an explicit `ordering` "
            "is given — sorts them nearest-first and annotates each with "
            "`distance_km`."
        ),
        parameters=_GEO_PARAMS,
    ),
    retrieve=extend_schema(
        tags=["Rooms"],
        summary="Retrieve a room",
        description="Public room detail, including images, owner profile, and nearby landmarks.",
    ),
    create=extend_schema(
        tags=["Rooms"],
        summary="Create a room",
        description="Create a listing owned by the authenticated user. Landlord flow.",
        examples=[
            OpenApiExample(
                "Create room",
                value={
                    "title": "Sunny Studio in Dhanmondi",
                    "description": "Fully furnished studio with balcony.",
                    "room_type": "studio",
                    "price": "15000.00",
                    "area": "Dhanmondi",
                    "address": "Road 7, Dhanmondi, Dhaka",
                    "lat": "23.746000",
                    "lng": "90.376000",
                    "amenities": ["WiFi", "AC"],
                    "gender_preference": "any",
                    "size_sqft": 350,
                    "is_available": True,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(tags=["Rooms"], summary="Update a room (owner only)"),
    partial_update=extend_schema(tags=["Rooms"], summary="Partially update a room (owner only)"),
    destroy=extend_schema(tags=["Rooms"], summary="Delete a room (owner only)"),
)
class RoomViewSet(viewsets.ModelViewSet):
    """CRUD for room listings, plus geo/map query support.

    Reads (`list`/`retrieve`) are public; writes require authentication and,
    for an existing room, ownership (`IsOwnerOrReadOnly`).
    """

    queryset = Room.objects.select_related("owner").prefetch_related("images").all()
    filterset_class = RoomFilter
    # Search v2: full-text on Postgres (with typo tolerance) / icontains
    # fallback on SQLite, applied manually in `filter_queryset` (SearchFilter
    # is a plain icontains across fields and can't rank or fuzzy-match).
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        OrderingFilter,
    ]
    ordering_fields = ["price", "rating", "created_at"]
    ordering = ["-created_at"]

    # Paid-tier ranking: premium > featured > free, newest first within a
    # tier. Applied when the client didn't ask for an explicit ordering (or
    # a geo reference point, which sorts nearest-first) — promotion should
    # surface promoted listings first, but never override a user's explicit
    # sort choice. Uses `effective_tier` (see get_queryset) so expired
    # promotions drop back to the free rank.
    TIER_RANK = Case(
        When(effective_tier="premium", then=Value(0)),
        When(effective_tier="featured", then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )

    # KYC-verified landlords rank above unverified ones within the same paid
    # tier — a trust signal for tenants, not a paid feature.
    VERIFIED_RANK = Case(
        When(verified=True, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )

    def get_serializer_class(self):
        if self.action == "list":
            return RoomListSerializer
        if self.action == "retrieve":
            return RoomDetailSerializer
        return RoomCreateUpdateSerializer

    def get_permissions(self):
        if self.action in (
            "list",
            "retrieve",
            "landmarks",
            "tier_catalog",
            "geocode",
            "summary",
            "similar_images",
            "map_intel",
            "map_commute",
            "map_value",
            "map_affordability",
            "map_ideal_areas",
            "map_search",
        ):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # ----- geo query support ------------------------------------------------

    def _reference_point(self) -> tuple[float, float] | None:
        """Resolve the query's reference point from `near_landmark` (a slug)
        or an explicit `near_lat`/`near_lng` pair. Returns None if the request
        asked for neither; raises ValidationError on malformed input."""
        params = self.request.query_params

        landmark_key = params.get("near_landmark")
        if landmark_key:
            landmark = get_landmark(landmark_key)
            if landmark is None:
                raise ValidationError({"near_landmark": f"Unknown landmark '{landmark_key}'."})
            return (landmark.lat, landmark.lng)

        near_lat, near_lng = params.get("near_lat"), params.get("near_lng")
        if near_lat is None and near_lng is None:
            return None
        if near_lat is None or near_lng is None:
            raise ValidationError({"near_lat": "near_lat and near_lng must be supplied together."})
        try:
            return (float(near_lat), float(near_lng))
        except ValueError as exc:
            raise ValidationError({"near_lat": "near_lat/near_lng must be numbers."}) from exc

    def _apply_bbox(self, queryset):
        raw = self.request.query_params.get("bbox")
        if not raw:
            return queryset
        try:
            box = BoundingBox.parse(raw)
        except ValueError as exc:
            raise ValidationError({"bbox": str(exc)}) from exc
        return queryset.filter(
            lat__gte=box.min_lat,
            lat__lte=box.max_lat,
            lng__gte=box.min_lng,
            lng__lte=box.max_lng,
        )

    def _apply_radius(self, queryset, reference: tuple[float, float]):
        raw = self.request.query_params.get("radius_km")
        if not raw:
            return queryset
        try:
            radius = float(raw)
        except ValueError as exc:
            raise ValidationError({"radius_km": "radius_km must be a number."}) from exc
        if radius <= 0:
            raise ValidationError({"radius_km": "radius_km must be positive."})

        ref_lat, ref_lng = reference
        # Cheap indexable bounding-box pre-filter to discard far-away rows in
        # the DB, then an exact haversine refinement in Python on the small
        # survivor set — avoids a full-table trig scan (SQLite has no trig).
        d_lat = lat_delta_for_km(radius)
        d_lng = lng_delta_for_km(radius, ref_lat)
        prefiltered = queryset.filter(
            lat__gte=ref_lat - d_lat,
            lat__lte=ref_lat + d_lat,
            lng__gte=ref_lng - d_lng,
            lng__lte=ref_lng + d_lng,
        )
        # `.values()` (plain dicts) rather than `.only()` model instances —
        # the base queryset uses select_related("owner"), which can't coexist
        # with deferring columns on the same rows.
        matching_pks = [
            row["id"]
            for row in prefiltered.values("id", "lat", "lng")
            if haversine_km(ref_lat, ref_lng, float(row["lat"]), float(row["lng"])) <= radius
        ]
        return queryset.filter(pk__in=matching_pks)

    def _order_by_distance(self, queryset, reference: tuple[float, float]):
        """Order a (already geo-filtered, hence small) queryset nearest-first,
        preserving it as a queryset so pagination still works — the Python sort
        result is projected back via a Case/When on primary key."""
        ref_lat, ref_lng = reference
        ranked = sorted(
            queryset.values("id", "lat", "lng"),
            key=lambda row: haversine_km(ref_lat, ref_lng, float(row["lat"]), float(row["lng"])),
        )
        if not ranked:
            return queryset
        ordering = Case(
            *[When(pk=row["id"], then=position) for position, row in enumerate(ranked)],
            output_field=IntegerField(),
        )
        return queryset.filter(pk__in=[row["id"] for row in ranked]).order_by(ordering)

    def get_queryset(self):
        queryset = super().get_queryset()

        # Expired promotions stop conferring benefits immediately: a listing
        # whose tier_expires_at is in the past is treated as free (both for
        # the tier_rank ordering below and for serialized output), so a paid
        # promotion can never silently outlive its purchased period.
        from django.db.models import Q
        from django.utils import timezone

        expired = Q(tier_expires_at__lte=timezone.now())
        queryset = queryset.annotate(
            effective_tier=Case(
                When(expired, then=Value(Room.Tier.FREE)),
                default="tier",
                output_field=models.CharField(max_length=10),
            )
        )

        if self.action != "list":
            return queryset

        queryset = self._apply_bbox(queryset)
        reference = self._reference_point()
        if reference is not None:
            queryset = self._apply_radius(queryset, reference)
        return queryset

    def filter_queryset(self, queryset):
        # Backends (django-filter, OrderingFilter's default `-created_at`) run
        # first; distance ordering is applied *after* so it isn't clobbered.
        # Nearest-first is the natural default for a "near X" query, but an
        # explicit ?ordering= (price, rating, …) must still win.
        queryset = super().filter_queryset(queryset)
        query_text = self.request.query_params.get("q")
        smart = self.request.query_params.get("smart") == "1"
        # Attached to the list response so the UI can render "what AI
        # understood" chips (budget/area/move-in month).
        self.nl_parsed = None
        semantically_ordered = False

        if self.action == "list" and query_text:
            from .search import search_rooms

            if smart:
                # Smart mode: keyword AND-matching would kill natural-language
                # queries ("১০ হাজার এর মধ্যে gulshan" shares no literal term
                # with any listing), so skip the strict pre-filter entirely:
                # 1. NL parsing turns budget/area/type/gender words into real
                #    filters over the full set;
                # 2. the surviving pool is ranked by vector similarity
                #    (semantic discovery — "student room near Gulshan" can
                #    still surface a listing that never says "student").
                parsed = parse_nl_query(query_text)
                self.nl_parsed = parsed
                if parsed["areas"]:
                    queryset = queryset.filter(area__in=parsed["areas"])
                if parsed["budget_max"]:
                    queryset = queryset.filter(price__lte=parsed["budget_max"])
                if parsed["room_type"]:
                    queryset = queryset.filter(room_type=parsed["room_type"])
                if parsed["gender"]:
                    queryset = queryset.filter(gender_preference__in=[parsed["gender"], "any"])

                pool_ids = list(queryset.values_list("id", flat=True))
                # Debug-only ranking transparency (settings.DEBUG or an
                # explicit ?debug_rank=1) — never exposed to normal users.
                debug_rank = bool(
                    settings.DEBUG or self.request.query_params.get("debug_rank") == "1"
                )
                if getattr(settings, "SEMANTIC_SEARCH_ENABLED", True):
                    rank_result = hybrid_rank(
                        query_text,
                        pool_ids,
                        user=self.request.user,
                        include_metadata=debug_rank,
                    )
                else:
                    # Legacy TF-IDF/LSA-only ranking when neural search is
                    # disabled via the SEMANTIC_SEARCH_ENABLED flag.
                    legacy = semantic_candidates(query_text, pool_ids)
                    rank_result = (
                        {"ids": [room_id for room_id, _score in legacy], "metadata": {}}
                        if legacy is not None
                        else None
                    )
                if rank_result:
                    ranked_ids = rank_result["ids"]
                    ordering = Case(
                        *[
                            When(pk=room_id, then=Value(position))
                            for position, room_id in enumerate(ranked_ids)
                        ],
                        output_field=IntegerField(),
                    )
                    queryset = queryset.filter(pk__in=ranked_ids).order_by(ordering)
                    semantically_ordered = True
                    if debug_rank:
                        self.rank_meta = rank_result.get("metadata", {})
            else:
                queryset = search_rooms(queryset, query_text)

        if self.action == "list" and not self.request.query_params.get("ordering"):
            reference = self._reference_point()
            if reference is not None:
                queryset = self._order_by_distance(queryset, reference)
            elif semantically_ordered:
                # Smart-search ordering already applied above.
                pass
            else:
                # Default browse view: rooms the user recently viewed or
                # wishlisted float up (personal boost), then promoted
                # listings, then KYC-verified landlords, then newest.
                queryset = self._apply_personal_boost(queryset)
                queryset = queryset.annotate(
                    tier_rank=self.TIER_RANK, verified_rank=self.VERIFIED_RANK
                ).order_by("personal_boost", "tier_rank", "verified_rank", "-created_at")
        return queryset

    def list(self, request, *args, **kwargs):
        """Attach the smart-search parse result (and debug rank metadata) to
        the list response."""
        response = super().list(request, *args, **kwargs)
        parsed = getattr(self, "nl_parsed", None)
        rank_meta = getattr(self, "rank_meta", None)
        if parsed is not None or rank_meta:
            if isinstance(response.data, dict):
                if parsed is not None:
                    response.data["nl_parsed"] = parsed
                if rank_meta:
                    response.data["rank_meta"] = rank_meta
            else:
                response.data = {
                    "results": response.data,
                    "nl_parsed": parsed,
                    "rank_meta": rank_meta,
                }
        return response

    def _apply_personal_boost(self, queryset):
        """Annotate `personal_boost` from the user's recent views + wishlist.

        Browsing order becomes: most recently viewed rooms first, then
        wishlisted, then the default tier/verified ranking. Only applies to
        authenticated users and only when no explicit ordering was requested
        (explicit sorts and map distance ordering always win).
        """
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            return queryset.annotate(personal_boost=Value(0, output_field=IntegerField()))

        from datetime import timedelta

        from django.utils import timezone

        cutoff = timezone.now() - timedelta(days=30)
        viewed_ids = list(
            RoomView.objects.filter(viewer=user, viewed_at__gte=cutoff)
            .order_by("-viewed_at")
            .values_list("room_id", flat=True)[:20]
        )
        wishlisted_ids = list(
            Wishlist.objects.filter(user=user).values_list("room_id", flat=True)[:20]
        )
        if not viewed_ids and not wishlisted_ids:
            return queryset.annotate(personal_boost=Value(0, output_field=IntegerField()))

        clauses = [When(pk=room_id, then=Value(rank)) for rank, room_id in enumerate(viewed_ids)]
        next_rank = len(viewed_ids)
        seen = set(viewed_ids)
        for room_id in wishlisted_ids:
            if room_id not in seen:
                clauses.append(When(pk=room_id, then=Value(next_rank)))
                next_rank += 1
                seen.add(room_id)
        return queryset.annotate(
            personal_boost=Case(*clauses, default=Value(next_rank), output_field=IntegerField())
        )

    def retrieve(self, request, *args, **kwargs):
        """Log a RoomView for landlord-insight counts, then render normally.

        Deduped per (viewer, room) within 5 minutes — page refreshes don't
        inflate the tally the way genuinely separate visits should.
        """
        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            self._record_view(request, kwargs.get("pk"))
        return response

    def _record_view(self, request, room_id) -> None:
        if not room_id:
            return
        user = getattr(request, "user", None)
        # Anonymous visitors aren't tracked (we don't cookie users), so counts
        # are a lower bound on traffic — but a consistent, comparable one.
        if user is None or not user.is_authenticated:
            return
        from datetime import timedelta

        from django.utils import timezone

        cutoff = timezone.now() - timedelta(minutes=5)
        already = RoomView.objects.filter(
            room_id=room_id,
            viewer=user,
            viewed_at__gte=cutoff,
        ).exists()
        if already:
            return
        # Analytics must never break room reads — ignore any DB hiccup.
        from contextlib import suppress

        with suppress(Exception):
            RoomView.objects.create(room_id=room_id, viewer=user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Only meaningful on list, and only when a reference point was given —
        # lets the serializer emit `distance_km` for "X km away" rendering.
        if self.action == "list":
            try:
                context["reference_point"] = self._reference_point()
            except ValidationError:
                # A malformed reference point is surfaced by get_queryset as a
                # 400; don't also raise while building context.
                context["reference_point"] = None
        return context

    @extend_schema(
        tags=["Rooms"],
        summary="List map landmarks",
        description="Static set of universities and metro stations used for map layers and "
        "the `near_landmark` filter. Public, unpaginated.",
        responses=LandmarkSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def landmarks(self, request):
        return Response(LandmarkSerializer(ALL_LANDMARKS, many=True).data)

    @extend_schema(
        tags=["Rooms"],
        summary="Street search / autocomplete",
        description="Search the curated Dhaka street & area gazetteer plus map landmarks "
        "(universities, metro stations) for a place-name query. Used by the map's "
        "search box to fly to a street/area and start a radius search there. "
        "Public, unpaginated, returns at most 8 suggestions.",
        parameters=[
            OpenApiParameter(
                "q",
                str,
                description="Place-name query, e.g. `mirpur`, `gulshan avenue`, `shahbagh`.",
            )
        ],
    )
    @action(detail=False, methods=["get"])
    def geocode(self, request):
        query = request.query_params.get("q", "")
        if not query.strip():
            return Response([])

        suggestions = []
        for street in search_streets(query):
            suggestions.append(
                {
                    "key": street.key,
                    "label": street.name,
                    "kind": street.kind,
                    "lat": street.lat,
                    "lng": street.lng,
                }
            )
        # Merge in matching landmarks so "mirpur 10" finds the station too.
        q_lower = query.strip().lower()
        for landmark in ALL_LANDMARKS:
            if q_lower in landmark.name.lower() or q_lower in landmark.key.lower():
                suggestions.append(
                    {
                        "key": landmark.key,
                        "label": landmark.name,
                        "kind": landmark.kind.value,
                        "lat": landmark.lat,
                        "lng": landmark.lng,
                    }
                )

        # Gazetteer / landmark miss? Ask OSM Nominatim (Dhaka-bounded,
        # best-effort) so the search box still answers streets the curated
        # list doesn't cover. Only on a total miss — for queries the gazetteer
        # already answers we don't hit the external service at all. Dedupe by
        # key in case the provider echoes the same place twice.
        if not suggestions and len(query.strip()) >= 3:
            seen = {s["key"] for s in suggestions}
            for hit in nominatim_search(query, limit=8):
                if hit["key"] not in seen:
                    suggestions.append(hit)
                    seen.add(hit["key"])

        return Response(suggestions[:8])

    @extend_schema(
        tags=["Rooms"],
        summary="Map room-count summary",
        description="Aggregate counts (total, available, price stats) for the current map "
        "viewport or radius — a cheap COUNT/AVG alternative to fetching the full "
        "paginated room list just to render a badge. Accepts the same geo filters "
        "as the list endpoint (`bbox`, `near_lat`/`near_lng`/`near_landmark` with "
        "`radius_km`) plus an `area` filter.",
        parameters=[
            *_GEO_PARAMS,
            OpenApiParameter("area", str, description="Filter to a single area (e.g. `Mirpur`)."),
        ],
    )
    @extend_schema(
        tags=["Rooms"],
        summary="Rooms summary (map chips + stats)",
        description=(
            "Aggregate counts and price stats for the room search — with the same "
            "bbox/radius/area filters as the list endpoint, so the map's area "
            "chips and the stats bar always match the visible listings."
        ),
        responses=inline_serializer(
            "RoomsSummaryResponse",
            fields={
                "total": serializers.IntegerField(),
                "available": serializers.IntegerField(),
                "avg_price": serializers.FloatField(allow_null=True),
                "min_price": serializers.FloatField(allow_null=True),
                "max_price": serializers.FloatField(allow_null=True),
                "by_area": serializers.ListField(
                    child=inline_serializer(
                        "RoomsSummaryAreaCount",
                        fields={
                            "area": serializers.CharField(),
                            "count": serializers.IntegerField(),
                            "lat": serializers.FloatField(required=False),
                            "lng": serializers.FloatField(required=False),
                        },
                    )
                ),
            },
        ),
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = Room.objects.all()
        queryset = self._apply_bbox(queryset)
        reference = self._reference_point()
        if reference is not None:
            queryset = self._apply_radius(queryset, reference)

        area = request.query_params.get("area")
        if area:
            queryset = queryset.filter(area__iexact=area)

        agg = queryset.aggregate(
            total=models.Count("id"),
            available=models.Count("id", filter=models.Q(is_available=True)),
            avg_price=models.Avg("price"),
            min_price=models.Min("price"),
            max_price=models.Max("price"),
        )
        # Count *available* rooms per area so the chips' numbers match the
        # badge's "N of M available" framing — a chip showing "Dhanmondi 3"
        # leads only to bookable listings.
        by_area = (
            queryset.filter(is_available=True)
            .values("area")
            .annotate(count=models.Count("id"))
            .order_by("-count", "area")
        )
        return Response(
            {
                "total": agg["total"],
                "available": agg["available"],
                "avg_price": round(float(agg["avg_price"]), 2)
                if agg["avg_price"] is not None
                else None,
                "min_price": float(agg["min_price"]) if agg["min_price"] is not None else None,
                "max_price": float(agg["max_price"]) if agg["max_price"] is not None else None,
                "by_area": [
                    {
                        "area": row["area"],
                        "count": row["count"],
                        # Fly-to point for the map's area chips, when known.
                        **(
                            {"lat": center[0], "lng": center[1]}
                            if (center := area_center(row["area"]))
                            else {}
                        ),
                    }
                    for row in by_area
                ],
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="Rooms with similar photos",
        description=(
            "Visual discovery: rooms whose primary photo looks like this one, "
            "nearest perceptual-hash distance first. Best-effort — rooms "
            "without readable photos are simply omitted."
        ),
        parameters=[
            OpenApiParameter(
                "limit", int, description="Max matches to return (default 8).", required=False
            )
        ],
    )
    @action(detail=True, methods=["get"], url_path="similar-images")
    def similar_images(self, request, pk=None):
        room = self.get_object()
        limit = int(request.query_params.get("limit", 8) or 8)
        matches = similar_rooms(room, top_k=limit)
        serializer = RoomListSerializer(
            [match[0] for match in matches],
            many=True,
            context=self.get_serializer_context(),
        )
        data = serializer.data
        for item, (_room, distance) in zip(data, matches, strict=False):
            item["phash_distance"] = distance
        return Response(data)

    # ----- Intelligent Rental Decision Map (Phase 7 v2) --------------------

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Area intelligence stats",
        description=(
            "Per-area aggregates for the map's Area Intelligence panel: average/median "
            "rent, listing counts, average size, demand (views/saves/bookings vs supply), "
            "metro access and price trend. Optional `area` filter for one area. "
            "Everything is calculated from live platform data; areas without data "
            "report nulls, never invented numbers."
        ),
        parameters=[
            OpenApiParameter(
                "area", str, required=False, description="Single area name (e.g. `Uttara`)."
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/stats")
    def map_intel(self, request):
        area = request.query_params.get("area")
        return Response(area_statistics(area))

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Commute ETA between two points",
        description=(
            "Travel-time estimate between two coordinates for walking/driving "
            "(straight-line heuristics) or transit (MRT Line-6 interpolation when "
            "both ends are within 1.2 km of a station). Estimates are labelled "
            "`estimate: true`; transit returns `minutes: null` with an honest "
            "explanation when routing isn't available."
        ),
        parameters=[
            OpenApiParameter("from_lat", float),
            OpenApiParameter("from_lng", float),
            OpenApiParameter("to_lat", float),
            OpenApiParameter("to_lng", float),
            OpenApiParameter(
                "mode", str, required=False, description="walking | driving | transit"
            ),
        ],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/commute")
    def map_commute(self, request):
        try:
            from_lat = float(request.query_params["from_lat"])
            from_lng = float(request.query_params["from_lng"])
            to_lat = float(request.query_params["to_lat"])
            to_lng = float(request.query_params["to_lng"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                {"detail": "from_lat/from_lng/to_lat/to_lng must all be numbers."}
            ) from exc
        mode = request.query_params.get("mode", "walking")
        if mode not in ("walking", "driving", "transit"):
            raise ValidationError({"mode": "mode must be walking, driving or transit."})
        eta = commute_eta(from_lat, from_lng, to_lat, to_lng, mode)
        return Response(
            {
                "mode": eta.mode,
                "minutes": eta.minutes,
                "distance_km": eta.distance_km,
                "estimate": eta.estimate,
                "detail": eta.detail,
            }
        )

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Listing value scores",
        description=(
            "Transparent 0-100 value scores for a comma-separated list of room ids "
            "(`ids=1,2,3`). Blend of price fit vs the area market, amenities, "
            "listing quality, verification, demand and metro access — weights in "
            "settings. Never exposes internal fraud scores."
        ),
        parameters=[OpenApiParameter("ids", str, description="Comma-separated room ids.")],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/value")
    def map_value(self, request):
        raw = request.query_params.get("ids", "")
        ids = [int(i) for i in raw.split(",") if i.strip().isdigit()]
        rooms = Room.objects.filter(pk__in=ids).only(
            "id", "price", "area", "room_type", "amenities", "verified", "lat", "lng", "updated_at"
        )
        return Response({r.id: value_score(r) for r in rooms})

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Affordability by area",
        description=(
            "Percentage of currently listed rooms per area that fit a budget "
            "(`budget=12000`). Used by the map's affordability layer — real "
            "listing shares, not an arbitrary score."
        ),
        parameters=[OpenApiParameter("budget", float)],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/affordability")
    def map_affordability(self, request):
        try:
            budget = float(request.query_params.get("budget", 0))
        except ValueError as exc:
            raise ValidationError({"budget": "budget must be a number."}) from exc
        if budget <= 0:
            raise ValidationError({"budget": "budget must be positive."})
        return Response(affordability_stats(budget))

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Ideal areas for a user profile",
        description=(
            "Ranked area recommendations from budget fit + commute (optional work "
            "point + max minutes) + availability + metro access, each with "
            "explainable reasons built from the same calculated facts."
        ),
        parameters=[
            OpenApiParameter("budget", float),
            OpenApiParameter("work_lat", float, required=False),
            OpenApiParameter("work_lng", float, required=False),
            OpenApiParameter("max_commute", int, required=False, description="Default 45 min"),
            OpenApiParameter("room_type", str, required=False),
        ],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/ideal-areas")
    def map_ideal_areas(self, request):
        try:
            budget = float(request.query_params.get("budget", 0))
        except ValueError as exc:
            raise ValidationError({"budget": "budget must be a number."}) from exc
        if budget <= 0:
            raise ValidationError({"budget": "budget must be positive."})
        work_lat = request.query_params.get("work_lat")
        work_lng = request.query_params.get("work_lng")
        try:
            lat = float(work_lat) if work_lat else None
            lng = float(work_lng) if work_lng else None
        except ValueError as exc:
            raise ValidationError({"work_lat": "work_lat/work_lng must be numbers."}) from exc
        max_commute = int(request.query_params.get("max_commute", 45) or 45)
        room_type = request.query_params.get("room_type") or None
        return Response(ideal_areas(budget, lat, lng, max_commute, room_type))

    @extend_schema(
        tags=["Map Intelligence"],
        summary="Natural-language map search",
        description=(
            "Turn a Bangla/English/Banglish query into a structured, map-actionable "
            "intent: filters (area/budget/type/amenities/metro-walk) + the matching "
            "rooms + a fly-to target (area centre or nearest metro) so the map can "
            "zoom, filter and render in one call. Example: 'উত্তরায় ১২ হাজারের মধ্যে "
            "metro station থেকে ১০ মিনিট walking distance-এর মধ্যে furnished room'."
        ),
        parameters=[OpenApiParameter("q", str, description="Free-text query.")],
    )
    @action(detail=False, methods=["get"], url_path="map-intel/search")
    def map_search(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"intent": parse_map_query(""), "rooms": [], "count": 0})
        intent = parse_map_query(q)
        rooms = map_search_rooms(intent)
        serializer = RoomListSerializer(
            rooms[:20], many=True, context=self.get_serializer_context()
        )
        # Fly-to target: area centre, or nearest metro when metro_walk asked.
        target: dict[str, Any] | None = None
        if intent["areas"]:
            centre = area_center(intent["areas"][0])
            if centre:
                target = {
                    "lat": centre[0],
                    "lng": centre[1],
                    "kind": "area",
                    "name": intent["areas"][0],
                }
        if intent.get("metro_walk") and rooms:
            best = min(
                (r for r in rooms if r.lat is not None and r.lng is not None),
                key=lambda r: nearest_metro_km(r) or 999,
                default=None,
            )
            if best is not None:
                station, _dist = nearest_metro_km(best, return_station=True)
                if station is not None:
                    target = {
                        "lat": station.lat,
                        "lng": station.lng,
                        "kind": "metro",
                        "name": station.name,
                    }
        return Response(
            {
                "query": q,
                "intent": intent,
                "count": len(rooms),
                "rooms": serializer.data,
                "target": target,
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="Listing tier catalog",
        description="Public price/benefit catalog for paid listing tiers (Free / Featured / "
        "Premium) and their duration, so the frontend can render the promotion "
        "UI without hardcoding prices.",
        responses=inline_serializer(
            "TierCatalogResponse",
            fields={
                "tiers": serializers.ListField(
                    child=inline_serializer(
                        "TierCatalogEntry",
                        fields={
                            "tier": serializers.CharField(),
                            "label": serializers.CharField(),
                            "price": serializers.FloatField(),
                            "benefits": serializers.ListField(child=serializers.CharField()),
                        },
                    )
                ),
                "duration_days": serializers.IntegerField(),
                "currency": serializers.CharField(),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="tier-catalog")
    def tier_catalog(self, request):
        pricing = settings.LISTING_TIER_PRICING
        return Response(
            {
                "tiers": [
                    {
                        "tier": "free",
                        "label": "Free",
                        "price": pricing["free"],
                        "benefits": [
                            "Standard placement in search",
                            "Up to 8 photos",
                            "Booking requests + chat",
                        ],
                    },
                    {
                        "tier": "featured",
                        "label": "Featured",
                        "price": pricing["featured"],
                        "benefits": [
                            "Boosted above free listings",
                            "Featured badge on card",
                            "Shown in Featured Rooms on home",
                        ],
                    },
                    {
                        "tier": "premium",
                        "label": "Premium",
                        "price": pricing["premium"],
                        "benefits": [
                            "Top of search results",
                            "Premium badge + highlighted card",
                            "Priority in AI recommendations",
                        ],
                    },
                ],
                "duration_days": settings.LISTING_TIER_DURATION_DAYS,
                "currency": "BDT",
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="Landlord listing insights",
        description=(
            "Per-listing engagement for the authenticated landlord: views (7/30d), "
            "wishlist saves, booking requests and approvals, and how each room's "
            "price compares to its area/type market average. Admin sees all rooms."
        ),
        responses=inline_serializer(
            "RoomsInsightsResponse",
            fields={
                "rooms": serializers.ListField(
                    child=inline_serializer(
                        "RoomsInsightRow",
                        fields={
                            "id": serializers.IntegerField(),
                            "title": serializers.CharField(),
                            "price": serializers.FloatField(),
                            "area": serializers.CharField(),
                            "room_type": serializers.CharField(),
                            "tier": serializers.CharField(),
                            "verified": serializers.BooleanField(),
                            "views_7d": serializers.IntegerField(),
                            "views_30d": serializers.IntegerField(),
                            "views_total": serializers.IntegerField(),
                            "wishlist_count": serializers.IntegerField(),
                            "booking_requests": serializers.IntegerField(),
                            "booking_approved": serializers.IntegerField(),
                            "area_avg_price": serializers.FloatField(allow_null=True),
                            "price_delta_pct": serializers.FloatField(allow_null=True),
                        },
                    )
                ),
                "summary": inline_serializer(
                    "RoomsInsightsSummary",
                    fields={
                        "listing_count": serializers.IntegerField(),
                        "total_views_30d": serializers.IntegerField(),
                        "total_wishlists": serializers.IntegerField(),
                    },
                ),
            },
        ),
    )
    @action(detail=False, methods=["get"], url_path="insights")
    def insights(self, request):
        """Aggregate engagement + price positioning for the owner's listings."""
        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        from bookings.models import Booking
        from pricing.models import MarketStat
        from rooms.listing_quality import get_listing_quality

        rooms_qs = self.get_queryset()
        if not (request.user.is_staff or request.user.role == request.user.Role.ADMIN):
            rooms_qs = rooms_qs.filter(owner=request.user)

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        market_stats = list(MarketStat.objects.all())
        market = {(m.area, m.room_type): float(m.avg_price) for m in market_stats}
        market_objects = {(m.area, m.room_type): m for m in market_stats}
        rooms = rooms_qs.annotate(
            views_7d=Count("views", filter=Q(views__viewed_at__gte=week_ago), distinct=True),
            views_30d=Count("views", filter=Q(views__viewed_at__gte=month_ago), distinct=True),
            views_total=Count("views", distinct=True),
            wishlist_count=Count("wishlisted_by", distinct=True),
            booking_requests=Count("bookings", distinct=True),
            booking_approved=Count(
                "bookings", filter=Q(bookings__status=Booking.Status.APPROVED), distinct=True
            ),
        )

        rows = []
        for room in rooms:
            area_avg = market.get((room.area, room.room_type))
            price = float(room.price)
            rows.append(
                {
                    "id": room.id,
                    "title": room.title,
                    "price": price,
                    "area": room.area,
                    "room_type": room.room_type,
                    "tier": room.tier,
                    "verified": room.verified,
                    "views_7d": room.views_7d,
                    "views_30d": room.views_30d,
                    "views_total": room.views_total,
                    "wishlist_count": room.wishlist_count,
                    "booking_requests": room.booking_requests,
                    "booking_approved": room.booking_approved,
                    "area_avg_price": area_avg,
                    "price_delta_pct": (
                        round((price - area_avg) / area_avg * 100, 1) if area_avg else None
                    ),
                    "listing_quality": get_listing_quality(room, market_objects),
                }
            )
        rows.sort(key=lambda r: r["views_30d"], reverse=True)
        total_views = sum(r["views_30d"] for r in rows)
        total_wishlists = sum(r["wishlist_count"] for r in rows)
        return Response(
            {
                "rooms": rows,
                "summary": {
                    "listing_count": len(rows),
                    "total_views_30d": total_views,
                    "total_wishlists": total_wishlists,
                },
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="Bulk create listings",
        description="Create several rooms in one request (landlord only). Body is a "
        "JSON array of the same room payloads accepted by POST /rooms/. "
        "Partially succeeds: valid rows are created, per-row errors are reported.",
        request=RoomCreateUpdateSerializer(many=True),
        responses=inline_serializer(
            "RoomsBulkCreateResponse",
            fields={
                "created": serializers.ListField(child=serializers.IntegerField()),
                "created_count": serializers.IntegerField(),
                "errors": serializers.ListField(
                    child=inline_serializer(
                        "RoomsBulkCreateError",
                        fields={
                            "index": serializers.IntegerField(),
                            "errors": serializers.DictField(child=serializers.CharField()),
                        },
                    )
                ),
            },
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk",
        permission_classes=[permissions.IsAuthenticated],
    )
    def bulk_create(self, request):
        """Create multiple listings from a JSON array; report per-row errors."""
        from .serializers import RoomCreateUpdateSerializer

        payload = request.data
        if not isinstance(payload, list):
            return Response(
                {"detail": "Request body must be a JSON array of room objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []
        for index, row in enumerate(payload):
            serializer = RoomCreateUpdateSerializer(data=row, context=self.get_serializer_context())
            if serializer.is_valid():
                room = serializer.save(owner=request.user)
                created.append(room.id)
            else:
                errors.append({"index": index, "errors": serializer.errors})

        return Response(
            {"created": created, "created_count": len(created), "errors": errors},
            status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )
