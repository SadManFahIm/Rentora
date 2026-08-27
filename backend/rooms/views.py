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
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttling import TrustedScopedRateThrottle
from wishlist.models import Wishlist

from .dhaka_areas import (
    boundary_feature_collection,
    hierarchy_payload,
    place_payload,
    search_places,
)
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
from .semantic import semantic_candidates
from .semantic_cache import cached_hybrid_rank
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


def _vector_rank(query_text: str, pool_ids: list[int]) -> dict | None:
    """Phase 16: push smart-search ranking down to pgvector embeddings.

    Active only when ``VECTOR_SEARCH_ENABLED`` and embeddings exist for the
    NL-filtered pool. Any failure returns ``None`` so the caller falls back to
    the in-process hybrid rank — vector search can never regress keyword search.
    """
    if not getattr(settings, "VECTOR_SEARCH_ENABLED", False):
        return None
    try:
        from embeddings.services import rooms_service

        service = rooms_service()
        if not pool_ids or not service.has_embeddings(pool_ids):
            return None
        matches = service.search_similar(query_text, top_k=len(pool_ids), candidate_ids=pool_ids)
        if not matches:
            return None
        return {
            "ids": [room_id for room_id, _score in matches],
            "metadata": {"rank": "pgvector", "top_k": len(matches)},
        }
    except Exception:
        return None


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
            "similar",
            "compare",
            "map_intel",
            "map_commute",
            "map_value",
            "map_affordability",
            "map_ideal_areas",
            "map_search",
            "area_hierarchy",
            "area_boundaries",
            "vision_search",
        ):
            return [permissions.AllowAny()]
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        if self.action in (
            "vision_analyze",
            "vision_analysis",
            "vision_description",
        ):
            # Owner-or-admin is enforced inside each action (admin must be
            # able to reach the endpoint; IsOwnerOrReadOnly would 403 staff).
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
                    # Phase 16: prefer the DB-backed pgvector ranking when it's
                    # live and has data for this pool; otherwise the existing
                    # same-query cache (Tier-1 quick win) which reuses the last
                    # ranking; bypassed for authenticated (personalized) and
                    # debug requests.
                    rank_result = _vector_rank(query_text, pool_ids)
                    if not rank_result:
                        rank_result = cached_hybrid_rank(
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
        # ETag-based caching: the list changes when rooms are added/updated,
        # so a short TTL avoids stale data while reducing redundant requests.
        response["Cache-Control"] = "private, max-age=60, stale-while-revalidate=30"
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
        response = Response(LandmarkSerializer(ALL_LANDMARKS, many=True).data)
        # Landmarks are static data — cache for 1 hour.
        response["Cache-Control"] = "public, max-age=3600"
        return response

    @extend_schema(
        tags=["Rooms"],
        summary="Compare listings side by side (AI Property Comparison)",
        description=(
            "Pass 2-5 room ids as `ids=1,2,3`. Returns a normalized comparison "
            "table: per-room fact cards, a column matrix (price, price/sqft, "
            "area, type, verified, amenities, market position, listing quality) "
            "and summary takeaways. Public — only public listing fields."
        ),
        parameters=[
            OpenApiParameter(
                "ids",
                str,
                description="Comma-separated room ids (2-5).",
            )
        ],
    )
    @action(detail=False, methods=["get"], url_path="compare")
    def compare(self, request):
        from .compare import compare_rooms

        raw = request.query_params.get("ids", "")
        ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
        if len(ids) < 2 or len(ids) > 5:
            return Response(
                {"detail": "Provide between 2 and 5 room ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rooms = list(Room.objects.filter(pk__in=ids, is_available=True))
        if len(rooms) < 2:
            return Response(
                {"detail": "At least two of the requested listings exist and are available."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(compare_rooms(rooms))

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
        # Structured Dhaka hierarchy first (sub-areas / neighbourhoods like
        # "Uttara Sector 7" or "Mirpur 10" resolve here with their parent
        # district), then the flat street gazetteer, then landmarks.
        seen_keys = set()
        for place in search_places(query):
            payload = place_payload(place)
            suggestions.append(
                {
                    "key": payload["key"],
                    "label": payload["name"],
                    "kind": "area",
                    "lat": payload["lat"],
                    "lng": payload["lng"],
                    "parent_name": payload["parent_name"],
                }
            )
            seen_keys.add(payload["key"])
        for street in search_streets(query):
            if street.key in seen_keys:
                continue
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
        summary="Dhaka area hierarchy",
        description="Structured geographic hierarchy of Dhaka — main areas with their "
        "sub-areas and neighbourhoods (approximate centres + parent links). "
        "Used by the map to render area labels, focus chips and area cards. "
        "Public, unpaginated.",
    )
    @action(detail=False, methods=["get"], url_path="area-hierarchy")
    def area_hierarchy(self, request):
        return Response(hierarchy_payload())

    @extend_schema(
        tags=["Rooms"],
        summary="Dhaka area boundary polygons",
        description="Approximate boundary bubbles (GeoJSON) for every Dhaka area — main "
        "areas, sub-areas and neighbourhoods, each labelled with an "
        "`approx_radius_km` since these are circles around real centres, not "
        "cadastral borders. The map renders them with zoom-based visibility "
        "(main areas at low zoom → neighbourhoods at high zoom). Public, "
        "unpaginated.",
    )
    @action(detail=False, methods=["get"], url_path="area-boundaries")
    def area_boundaries(self, request):
        response = Response(boundary_feature_collection())
        # Area boundaries are static data — cache for 1 hour.
        response["Cache-Control"] = "public, max-age=3600"
        return response

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

    @extend_schema(
        tags=["Rooms"],
        summary="Rooms with similar descriptions",
        description=(
            "Semantic discovery: public rooms whose listing text is closest to "
            "this one in embedding space (pgvector when enabled, in-process "
            "fallback otherwise). Best-effort — returns an empty list when no "
            "embeddings exist yet."
        ),
        parameters=[
            OpenApiParameter(
                "limit", int, description="Max matches to return (default 8).", required=False
            )
        ],
    )
    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request, pk=None):
        room = self.get_object()
        limit = int(request.query_params.get("limit", 8) or 8)
        query = " ".join(
            part
            for part in [room.title, room.area, room.description or "", room.address or ""]
            if part
        )
        try:
            from embeddings.services import search_similar_rooms

            matches = search_similar_rooms(query, top_k=limit, exclude_ids=[room.id])
        except Exception:
            matches = []
        if not matches:
            return Response([])
        rooms_by_id = {
            obj.id: obj for obj in Room.objects.filter(id__in=[rid for rid, _score in matches])
        }
        ordered = [rooms_by_id[rid] for rid, _score in matches if rid in rooms_by_id]
        serializer = RoomListSerializer(
            ordered,
            many=True,
            context=self.get_serializer_context(),
        )
        data = serializer.data
        score_by_id = {rid: score for rid, score in matches}
        for item in data:
            item["similarity"] = score_by_id.get(item["id"])
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
        summary="Per-listing price recommendation (owner/admin)",
        description=(
            "Demand-forecast + market + interest signals combined into a "
            "raise/hold/lower suggestion with a suggested price, a dynamic "
            "price (incl. demand-trend momentum, ±8% bounded), a safe test "
            "window and a 24h validity. Owner or admin only — a suggestion "
            "to review, never an automatic change."
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="price-recommendation",
        permission_classes=[permissions.IsAuthenticated],
    )
    def price_recommendation(self, request, pk=None):
        room = self.get_object()
        is_admin = request.user.is_staff or request.user.role == request.user.Role.ADMIN
        if room.owner_id != request.user.id and not is_admin:
            return Response(
                {"detail": "You can only see recommendations for your own listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Phase 15 — Monetization 2.0: the abstraction gates the v2
        # dynamic-pricing block behind the landlord plan entitlement.
        from subscriptions.services.predict import price_prediction_for

        return Response(price_prediction_for(request.user, room))

    @extend_schema(
        tags=["Rooms"],
        summary="Apply the recommended dynamic price (landlord plan)",
        description=(
            "Premium action (server-side entitlement 'price_prediction_v2'): "
            "writes the grounded dynamic price to the listing. Free-tier users "
            "can view the recommendation but cannot auto-apply it. Never "
            "auto-decides — this only runs on explicit landlord action."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="price-recommendation/apply",
        permission_classes=[permissions.IsAuthenticated],
    )
    def apply_price_recommendation(self, request, pk=None):
        from decimal import Decimal

        from django.db import transaction

        from audit.services import log_action
        from subscriptions.services.entitlements import check_entitlement

        room = self.get_object()
        is_admin = request.user.is_staff or request.user.role == request.user.Role.ADMIN
        if room.owner_id != request.user.id and not is_admin:
            return Response(
                {"detail": "You can only change your own listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not check_entitlement(request.user, "price_prediction_v2") and not is_admin:
            return Response(
                {
                    "detail": "Dynamic price application requires the price_prediction_v2 "
                    "entitlement (landlord plan)."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        from .price_recommendation import listing_price_recommendation

        recommendation = listing_price_recommendation(room)
        dynamic = recommendation.get("dynamic_price")
        if dynamic is None:
            return Response(
                {"detail": "No grounded dynamic price available right now."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            locked = Room.objects.select_for_update().get(pk=room.pk)
            if locked.owner_id != request.user.id and not is_admin:
                return Response(
                    {"detail": "You can only change your own listings."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            new_price = Decimal(str(dynamic))
            locked.price = new_price
            locked.save(update_fields=["price", "updated_at"])
            log_action(
                actor=request.user,
                action="room.price_applied",
                target=locked,
                detail={
                    "from": str(room.price),
                    "to": str(new_price),
                    "valid_until": recommendation.get("valid_until"),
                },
            )

        from analytics.services import record_event

        record_event(
            request.user,
            "price_applied",
            category="monetization",
            properties={"room_id": locked.pk, "price": str(new_price)},
            path="/dashboard",
        )
        return Response(
            {
                "room_id": locked.pk,
                "price": str(new_price),
                "valid_until": recommendation.get("valid_until"),
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="AI draft a listing description (authenticated)",
        description=(
            "Deterministic auto-draft of a title + description + amenity tags "
            "from the landlord's own fields (no LLM). Body mirrors the room "
            "create payload; returns a draft to review, never auto-publishes."
        ),
        request=inline_serializer(
            "GenerateDescriptionRequest",
            fields={
                "title": serializers.CharField(required=False, allow_blank=True),
                "room_type": serializers.CharField(required=False, default="single"),
                "price": serializers.DecimalField(max_digits=10, decimal_places=2, required=False),
                "area": serializers.CharField(required=False, default="Dhanmondi"),
                "size_sqft": serializers.IntegerField(required=False),
                "gender_preference": serializers.CharField(required=False, default="any"),
                "amenities": serializers.ListField(
                    child=serializers.CharField(), required=False, default=list
                ),
            },
        ),
        responses=inline_serializer(
            "GenerateDescriptionResponse",
            fields={
                "title": serializers.CharField(),
                "description": serializers.CharField(),
                "amenities": serializers.ListField(child=serializers.CharField()),
                "note": serializers.CharField(),
            },
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="generate-description",
        permission_classes=[permissions.IsAuthenticated],
    )
    def generate_description(self, request):
        from .description_generator import generate_listing_draft

        data = request.data or {}
        draft = generate_listing_draft(
            area=str(data.get("area", "Dhanmondi")),
            room_type=str(data.get("room_type", "single")),
            price=float(data["price"]) if data.get("price") not in (None, "") else None,
            size_sqft=int(data["size_sqft"]) if data.get("size_sqft") not in (None, "") else None,
            gender_preference=str(data.get("gender_preference", "any")),
            amenities=list(data.get("amenities") or []),
            title_hint=str(data.get("title", "")),
        )
        return Response(draft)

    # ----- Phase 14 — Vision & content AI -----------------------------------

    def _owner_or_admin(self, request, room) -> bool:
        is_admin = request.user.is_staff or request.user.role == request.user.Role.ADMIN
        return room.owner_id == request.user.id or is_admin

    @extend_schema(
        tags=["Rooms"],
        summary="Vision analysis of a listing's photos (owner/admin)",
        description=(
            "Deterministic photo intelligence: lighting / tone / décor / "
            "framing observations, a caption, the dominant colour palette and "
            "(with a configured gateway) suggested amenity tags. Statistical "
            "description of pixels — it cannot name specific furniture. "
            "Stored on the listing; re-run explicitly to refresh."
        ),
        responses=inline_serializer(
            "VisionAnalysisResponse",
            fields={
                "available": serializers.BooleanField(),
                "reason": serializers.CharField(required=False),
                "provider": serializers.CharField(required=False),
                "caption": serializers.CharField(required=False),
                "observations": serializers.ListField(
                    child=inline_serializer(
                        "VisionObservation",
                        fields={
                            "kind": serializers.CharField(),
                            "label": serializers.CharField(),
                            "confidence": serializers.FloatField(),
                        },
                    ),
                    required=False,
                ),
                "suggested_amenities": serializers.ListField(
                    child=serializers.CharField(), required=False
                ),
                "palette": serializers.ListField(
                    child=inline_serializer(
                        "VisionColour",
                        fields={
                            "hex": serializers.CharField(),
                            "name": serializers.CharField(),
                            "share": serializers.FloatField(),
                        },
                    ),
                    required=False,
                ),
                "photo_count": serializers.IntegerField(required=False),
                "note": serializers.CharField(required=False),
            },
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="vision/analyze",
        permission_classes=[permissions.IsAuthenticated],
    )
    def vision_analyze(self, request, pk=None):
        room = self.get_object()
        if not self._owner_or_admin(request, room):
            return Response(
                {"detail": "You can only analyse your own listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not settings.VISION_ENABLED:
            return Response(
                {"detail": "Vision features are disabled on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        from .models import RoomVisionAnalysis
        from .vision import analyze_listing

        analysis = analyze_listing(room, request)
        if not analysis.get("available"):
            return Response(analysis, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        RoomVisionAnalysis.objects.update_or_create(
            room=room,
            defaults={
                "provider": analysis["provider"],
                "caption": analysis["caption"],
                "observations": analysis["observations"],
                "suggested_amenities": analysis["suggested_amenities"],
                "palette": analysis["palette"],
                "photo_profiles": analysis["photo_profiles"],
            },
        )
        return Response(analysis)

    @extend_schema(
        tags=["Rooms"],
        summary="Stored vision analysis (owner/admin)",
        description="Return the last stored vision analysis for a listing, "
        "or 404 when it has never been analysed.",
        responses=inline_serializer(
            "VisionAnalysisStoredResponse",
            fields={
                "provider": serializers.CharField(),
                "caption": serializers.CharField(),
                "observations": serializers.ListField(
                    child=inline_serializer(
                        "VisionObservationStored",
                        fields={
                            "kind": serializers.CharField(),
                            "label": serializers.CharField(),
                            "confidence": serializers.FloatField(),
                        },
                    )
                ),
                "suggested_amenities": serializers.ListField(child=serializers.CharField()),
                "palette": serializers.ListField(
                    child=inline_serializer(
                        "VisionColourStored",
                        fields={
                            "hex": serializers.CharField(),
                            "name": serializers.CharField(),
                            "share": serializers.FloatField(),
                        },
                    )
                ),
                "updated_at": serializers.DateTimeField(),
            },
        ),
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="vision",
        permission_classes=[permissions.IsAuthenticated],
    )
    def vision_analysis(self, request, pk=None):
        room = self.get_object()
        if not self._owner_or_admin(request, room):
            return Response(
                {"detail": "You can only view analysis of your own listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from .models import RoomVisionAnalysis

        analysis = RoomVisionAnalysis.objects.filter(room=room).first()
        if analysis is None:
            return Response(
                {"detail": "No vision analysis stored for this listing yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "provider": analysis.provider,
                "caption": analysis.caption,
                "observations": analysis.observations,
                "suggested_amenities": analysis.suggested_amenities,
                "palette": analysis.palette,
                "updated_at": analysis.updated_at,
            }
        )

    @extend_schema(
        tags=["Rooms"],
        summary="AI draft from the listing's photos (owner/admin)",
        description=(
            "Draft title + description + amenity tags from the listing's real "
            "fields AND its actual photos (observations + caption + palette). "
            "Deterministic — every sentence is grounded in real inputs; a "
            "draft to review, never auto-published."
        ),
        responses=inline_serializer(
            "VisionDescriptionResponse",
            fields={
                "title": serializers.CharField(),
                "description": serializers.CharField(),
                "amenities": serializers.ListField(child=serializers.CharField()),
                "observations": serializers.ListField(
                    child=inline_serializer(
                        "VisionObservationDescription",
                        fields={
                            "kind": serializers.CharField(),
                            "label": serializers.CharField(),
                            "confidence": serializers.FloatField(),
                        },
                    )
                ),
                "note": serializers.CharField(),
            },
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="vision/description",
        permission_classes=[permissions.IsAuthenticated],
    )
    def vision_description(self, request, pk=None):
        room = self.get_object()
        if not self._owner_or_admin(request, room):
            return Response(
                {"detail": "You can only draft your own listings."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not settings.VISION_ENABLED:
            return Response(
                {"detail": "Vision features are disabled on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        from .description_generator import generate_listing_draft
        from .vision import analyze_listing

        analysis = analyze_listing(room, request)
        if not analysis.get("available"):
            return Response(
                {"detail": "This listing has no readable photos to draft from."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        brightness = {p["brightness_label"] for p in analysis["photo_profiles"]}
        draft = generate_listing_draft(
            area=str(room.area),
            room_type=str(room.room_type),
            price=float(room.price) if room.price is not None else None,
            size_sqft=room.size_sqft,
            gender_preference=str(room.gender_preference or "any"),
            amenities=list(room.amenities or []),
            title_hint=str(room.title or ""),
            image_profile={
                "available": True,
                "brightness": "bright" if "bright" in brightness else "normal",
                "colourfulness": analysis["photo_profiles"][0].get("colourfulness_label", "muted"),
            },
        )
        draft["description"] = f"{analysis['caption']} {draft['description']}"
        draft["observations"] = analysis["observations"]
        draft["note"] = (
            "Drafted from your listing details and its actual photos — "
            "review and edit before publishing."
        )
        return Response(draft)

    @extend_schema(
        tags=["Rooms"],
        summary="AI image search — upload a photo, find look-alike rooms",
        description=(
            "Upload a room photo and get the listings whose photos look most "
            "similar, ranked by a transparent 0-100 score (50% perceptual "
            "hash + 25% colour palette + 25% lighting). Deterministic and "
            "self-hosted; it finds visually similar rooms, not semantic "
            "object matches."
        ),
        request=inline_serializer(
            "VisionSearchRequest",
            fields={"image": serializers.ImageField()},
        ),
        responses=inline_serializer(
            "VisionSearchResponse",
            fields={
                "matches": serializers.ListField(
                    child=inline_serializer(
                        "VisionSearchMatch",
                        fields={
                            "room": RoomListSerializer(),
                            "match_score": serializers.IntegerField(),
                            "reasons": serializers.ListField(child=serializers.CharField()),
                        },
                    )
                ),
                "note": serializers.CharField(),
            },
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="vision/search",
        parser_classes=[MultiPartParser, FormParser],
    )
    def vision_search(self, request):
        # DRF's @action decorator does not accept throttle kwargs — apply the
        # dedicated vision scope manually so photo uploads can't be scripted.
        self.throttle_classes = [TrustedScopedRateThrottle]
        self.throttle_scope = "vision"
        self.check_throttles(request)
        if not settings.VISION_ENABLED:
            return Response(
                {"detail": "Vision features are disabled on this deployment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        from config.uploads import validate_image_upload

        image = request.FILES.get("image")
        if image is None:
            return Response(
                {"detail": "An image file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_image_upload(image, enforce_min_dimension=False)
        except ValidationError as exc:
            return Response(
                {"detail": exc.detail[0] if isinstance(exc.detail, list) else exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .vision import fingerprint_image, image_search

        query_bytes = image.read()
        if fingerprint_image(query_bytes) is None:
            return Response(
                {"detail": "Could not read the uploaded image — try a clear JPEG or PNG."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        matches = image_search(query_bytes)
        room_ids = [m["room_id"] for m in matches]
        rooms = list(Room.objects.filter(pk__in=room_ids))
        by_id = {room.pk: room for room in rooms}
        payload = []
        for match in matches:
            room = by_id.get(match["room_id"])
            if room is None:
                continue
            row = RoomListSerializer(room, context={"request": request}).data
            row["match_score"] = match["match_score"]
            row["reasons"] = match["reasons"]
            payload.append(row)
        return Response(
            {
                "matches": payload,
                "note": "Visual similarity from your photo — scores blend photo "
                "composition, colour palette and lighting. Deterministic, no "
                "external model.",
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


@extend_schema(
    tags=["Rooms"],
    summary="Commute ETA between two points",
    description=(
        "Road-network ETA (car/cng/bus) via OSRM with automatic fallback to "
        "the straight-line heuristic when routing is unavailable. Modes: "
        "car, cng, bus, driving, walking, transit. Response includes the "
        "`source` so clients can show 'approximate' for heuristic results."
    ),
)
class CommuteEtaView(APIView):
    """GET /api/v1/rooms/eta/?from_lat=..&from_lng=..&to_lat=..&to_lng=..&mode=car"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            from_lat = float(request.query_params["from_lat"])
            from_lng = float(request.query_params["from_lng"])
            to_lat = float(request.query_params["to_lat"])
            to_lng = float(request.query_params["to_lng"])
        except (KeyError, TypeError, ValueError):
            return Response(
                {"detail": "from_lat, from_lng, to_lat, to_lng are required numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mode = request.query_params.get("mode", "car")
        if mode not in ("car", "cng", "bus", "driving", "walking", "transit"):
            return Response(
                {"detail": f"Unsupported mode: {mode}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        estimate = commute_eta(from_lat, from_lng, to_lat, to_lng, mode)
        return Response(
            {
                "mode": estimate.mode,
                "minutes": estimate.minutes,
                "distance_km": estimate.distance_km,
                "estimate": estimate.estimate,
                "detail": estimate.detail,
                "source": "osrm" if "OSRM" in estimate.detail else "heuristic",
            }
        )
