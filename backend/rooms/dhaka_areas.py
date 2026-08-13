"""Structured Dhaka geographic hierarchy (Phase 7 v3).

The flat gazetteer in ``streets.py`` answers "where is X" but not "what is X
relative to Y". Tenants think in nested places — *Mirpur 10* is inside
*Mirpur*, *Uttara Sector 7* is inside *Uttara* — and area cards benefit from
that hierarchy (a sub-area knows its parent district, which is the value
used for `area=` filters and per-area stats).

This module is the single source of truth for that structure:

- **Main areas** are the canonical ``Room.Area`` choices (so a resolved place
  can be used directly as an ``area__in=`` filter).
- **Sub-areas / neighbourhoods** hang off a parent main area with their own
  approximate centre coordinates (same "good enough for city scale" policy as
  ``streets.py`` / ``landmarks.py``).
- Every entity carries Bangla + English aliases so map search and the NL
  parser recognise the same place names.

Coordinates are approximate real-world positions (hundreds of metres of
error is immaterial when the map flies to a neighbourhood). No fabricated
places — everything here is a real Dhaka locality.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DhakaPlace:
    key: str  # stable slug
    name: str  # display name
    kind: str  # "main_area" | "sub_area" | "neighborhood"
    parent: str | None  # parent key (None for main areas)
    lat: float
    lng: float
    aliases: tuple[str, ...] = ()


# Main areas mirror Room.Area choices — keep in sync with models.py.
MAIN_AREAS: tuple[DhakaPlace, ...] = (
    DhakaPlace("uttara", "Uttara", "main_area", None, 23.8759, 90.3795, ("উত্তরা",)),
    DhakaPlace("mirpur", "Mirpur", "main_area", None, 23.8223, 90.3654, ("মিরপুর",)),
    DhakaPlace("dhanmondi", "Dhanmondi", "main_area", None, 23.7461, 90.3742, ("ধানমন্ডি",)),
    DhakaPlace("gulshan", "Gulshan", "main_area", None, 23.7808, 90.4152, ("গুলশান",)),
    DhakaPlace("banani", "Banani", "main_area", None, 23.7937, 90.4066, ("বনানী",)),
    DhakaPlace("mohammadpur", "Mohammadpur", "main_area", None, 23.7623, 90.3588, ("মোহাম্মদপুর",)),
    DhakaPlace("azimpur", "Azimpur", "main_area", None, 23.7226, 90.3874, ("আজিমপুর",)),
    DhakaPlace("tejgaon", "Tejgaon", "main_area", None, 23.7600, 90.4000, ("তেজগাঁও",)),
    DhakaPlace("badda", "Badda", "main_area", None, 23.7740, 90.4230, ("বাড্ডা",)),
    DhakaPlace("rampura", "Rampura", "main_area", None, 23.7650, 90.4270, ("রামপুরা",)),
    DhakaPlace("banasree", "Banasree", "main_area", None, 23.7700, 90.4320, ("বনশ্রী",)),
    DhakaPlace("khilgaon", "Khilgaon", "main_area", None, 23.7470, 90.4180, ("খিলগাঁও",)),
    DhakaPlace("motijheel", "Motijheel", "main_area", None, 23.7330, 90.4170, ("মতিঝিল",)),
    DhakaPlace("old_dhaka", "Old Dhaka", "main_area", None, 23.7100, 90.4120, ("পুরান ঢাকা",)),
    DhakaPlace("bashundhara", "Bashundhara", "main_area", None, 23.8150, 90.4270, ("বসুন্ধরা",)),
    DhakaPlace("lalmatia", "Lalmatia", "main_area", None, 23.7600, 90.3670, ("লালমাটিয়া",)),
    DhakaPlace("shyamoli", "Shyamoli", "main_area", None, 23.7706, 90.3619, ("শ্যামলী",)),
    DhakaPlace("savar", "Savar", "main_area", None, 23.8583, 90.2668, ("সাভার",)),
    DhakaPlace("keraniganj", "Keraniganj", "main_area", None, 23.6800, 90.3600, ("কেরানীগঞ্জ",)),
    DhakaPlace("tongi", "Tongi", "main_area", None, 23.8900, 90.4050, ("টঙ্গী",)),
)

# Sub-areas and neighbourhoods with real, approximate centres. Parent keys
# reference MAIN_AREAS. Uttara sectors and Mirpur blocks are the most
# searched-for sub-localities, so they get full coverage; other areas list
# their well-known neighbourhoods.
SUB_AREAS: tuple[DhakaPlace, ...] = (
    # ---- Uttara sectors ----
    DhakaPlace(
        "uttara_sector_1",
        "Uttara Sector 1",
        "sub_area",
        "uttara",
        23.8665,
        90.3967,
        ("উত্তরা সেক্টর ১",),
    ),
    DhakaPlace(
        "uttara_sector_3",
        "Uttara Sector 3",
        "sub_area",
        "uttara",
        23.8688,
        90.3886,
        ("উত্তরা সেক্টর ৩",),
    ),
    DhakaPlace(
        "uttara_sector_4",
        "Uttara Sector 4",
        "sub_area",
        "uttara",
        23.8710,
        90.3830,
        ("উত্তরা সেক্টর ৪",),
    ),
    DhakaPlace(
        "uttara_sector_7",
        "Uttara Sector 7",
        "sub_area",
        "uttara",
        23.8670,
        90.3760,
        ("উত্তরা সেক্টর ৭",),
    ),
    DhakaPlace(
        "uttara_sector_10",
        "Uttara Sector 10",
        "sub_area",
        "uttara",
        23.8790,
        90.3850,
        ("উত্তরা সেক্টর ১০",),
    ),
    DhakaPlace(
        "uttara_sector_11",
        "Uttara Sector 11",
        "sub_area",
        "uttara",
        23.8830,
        90.3900,
        ("উত্তরা সেক্টর ১১",),
    ),
    DhakaPlace(
        "uttara_sector_12",
        "Uttara Sector 12",
        "sub_area",
        "uttara",
        23.8870,
        90.3940,
        ("উত্তরা সেক্টর ১২",),
    ),
    # ---- Mirpur blocks ----
    DhakaPlace("mirpur_1", "Mirpur 1", "sub_area", "mirpur", 23.8080, 90.3660, ("মিরপুর ১",)),
    DhakaPlace("mirpur_2", "Mirpur 2", "sub_area", "mirpur", 23.8100, 90.3580, ("মিরপুর ২",)),
    DhakaPlace("mirpur_10", "Mirpur 10", "sub_area", "mirpur", 23.8069, 90.3687, ("মিরপুর ১০",)),
    DhakaPlace("mirpur_11", "Mirpur 11", "sub_area", "mirpur", 23.8180, 90.3654, ("মিরপুর ১১",)),
    DhakaPlace("mirpur_12", "Mirpur 12", "sub_area", "mirpur", 23.8240, 90.3680, ("মিরপুর ১২",)),
    DhakaPlace("mirpur_pallabi", "Pallabi", "sub_area", "mirpur", 23.8250, 90.3648, ("পল্লবী",)),
    # ---- Dhanmondi roads ----
    DhakaPlace(
        "dhanmondi_8", "Dhanmondi 8", "sub_area", "dhanmondi", 23.7480, 90.3715, ("ধানমন্ডি ৮",)
    ),
    DhakaPlace(
        "dhanmondi_15", "Dhanmondi 15", "sub_area", "dhanmondi", 23.7440, 90.3750, ("ধানমন্ডি ১৫",)
    ),
    DhakaPlace(
        "dhanmondi_27", "Dhanmondi 27", "sub_area", "dhanmondi", 23.7434, 90.3773, ("ধানমন্ডি ২৭",)
    ),
    DhakaPlace(
        "satmasjid_road",
        "Satmasjid Road",
        "neighborhood",
        "dhanmondi",
        23.7480,
        90.3715,
        ("সাতমসজিদ রোড",),
    ),
    # ---- East-side neighbourhoods ----
    DhakaPlace("malibagh", "Malibagh", "neighborhood", "rampura", 23.7540, 90.4050, ("মালিবাগ",)),
    DhakaPlace("moghbazar", "Moghbazar", "neighborhood", "tejgaon", 23.7540, 90.3980, ("মগবাজার",)),
    DhakaPlace("eskaton", "Eskaton", "neighborhood", "tejgaon", 23.7430, 90.3970, ("এস্কাটন",)),
    DhakaPlace(
        "nayapaltan", "Nayapaltan", "neighborhood", "motijheel", 23.7410, 90.4020, ("নয়াপল্টন",)
    ),
    DhakaPlace("shahbagh", "Shahbagh", "neighborhood", "dhanmondi", 23.7380, 90.3960, ("শাহবাগ",)),
    DhakaPlace("farmgate", "Farmgate", "neighborhood", "tejgaon", 23.7580, 90.3894, ("ফার্মগেট",)),
    DhakaPlace("mohakhali", "Mohakhali", "neighborhood", "banani", 23.7750, 90.4030, ("মোহাখালী",)),
    DhakaPlace("kuril", "Kuril", "neighborhood", "bashundhara", 23.8180, 90.4230, ("কুড়িল",)),
    DhakaPlace("kalabagan", "Kalabagan", "neighborhood", "dhanmondi", 23.7490, 90.3780, ("কলাবাগান",)),
    DhakaPlace(
        "panthapath", "Panthapath", "neighborhood", "dhanmondi", 23.7510, 90.3875, ("পান্থপথ",)
    ),
    DhakaPlace(
        "kawran_bazar", "Kawran Bazar", "neighborhood", "tejgaon", 23.7500, 90.3920, ("কাওরান বাজার",)
    ),
    DhakaPlace("agargaon", "Agargaon", "neighborhood", "shyamoli", 23.7779, 90.3800, ("আগারগাঁও",)),
    DhakaPlace("kallyanpur", "Kallyanpur", "neighborhood", "mirpur", 23.7870, 90.3470, ("কল্যাণপুর",)),
    DhakaPlace(
        "hatirjheel", "Hatirjheel", "neighborhood", "banani", 23.7760, 90.4090, ("হাতিরঝিল",)
    ),
)

ALL_PLACES: tuple[DhakaPlace, ...] = MAIN_AREAS + SUB_AREAS

_BY_KEY: dict[str, DhakaPlace] = {p.key: p for p in ALL_PLACES}


def get_place(key: str) -> DhakaPlace | None:
    """Resolve a place by its slug, or None."""
    return _BY_KEY.get(key)


def children_of(parent_key: str) -> list[DhakaPlace]:
    """Sub-areas/neighbourhoods whose parent is ``parent_key``, key-sorted."""
    return sorted(
        (p for p in SUB_AREAS if p.parent == parent_key),
        key=lambda p: p.key,
    )


def search_places(query: str, limit: int = 8) -> list[DhakaPlace]:
    """Ranked place matches for an autocomplete query.

    Same policy as ``streets.search_streets``: case-insensitive substring
    pass over display name + aliases, prefix matches outrank contains
    matches, main areas outrank sub-areas (a whole district is more
    actionable than a sector when the query is generic).
    """
    q = query.strip().lower()
    if not q:
        return []

    scored: list[tuple[int, DhakaPlace]] = []
    for place in ALL_PLACES:
        candidates = (place.name, *place.aliases)
        best = None
        for text in candidates:
            lower = text.lower()
            if lower.startswith(q):
                best = 0 if place.kind == "main_area" else 1
                break
            if q in lower and best is None:
                best = 2 if place.kind == "main_area" else 3
        if best is not None:
            scored.append((best, place))

    scored.sort(key=lambda pair: (pair[0], pair[1].name.lower()))
    return [place for _, place in scored[:limit]]


def place_payload(place: DhakaPlace) -> dict:
    """API shape for a place — parent chain resolved to names."""
    parent_name = None
    if place.parent:
        parent = _BY_KEY.get(place.parent)
        parent_name = parent.name if parent else place.parent
    return {
        "key": place.key,
        "name": place.name,
        "kind": place.kind,
        "parent": place.parent,
        "parent_name": parent_name,
        "lat": place.lat,
        "lng": place.lng,
    }


def hierarchy_payload() -> dict:
    """Full tree for the area-hierarchy endpoint: main areas with children."""
    return {
        "main_areas": [
            {
                **place_payload(main),
                "children": [place_payload(c) for c in children_of(main.key)],
            }
            for main in MAIN_AREAS
        ]
    }
