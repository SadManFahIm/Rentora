"""Static Dhaka landmark reference data for room proximity features.

Hardcoded on purpose (Phase 7 decision): the set of major universities and
MRT Line 6 metro stations in Dhaka is small and stable, so it lives in code
rather than a DB table — no admin CRUD, no migrations, and proximity stays a
pure, side-effect-free computation over this list.

If landmarks ever need to be user-editable, promote this to a `landmarks`
app with its own model; nothing else in the geo layer would have to change,
since everything downstream only consumes `ALL_LANDMARKS` / `get_landmark`.

Coordinates are approximate real-world positions, good enough for
"how far is this room from X" at city scale (hundreds of metres of error is
immaterial when the answer is rendered as "1.2 km from Dhaka University").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LandmarkKind(Enum):
    UNIVERSITY = "university"
    METRO = "metro"


@dataclass(frozen=True)
class Landmark:
    key: str  # stable slug — the value accepted by `?near_landmark=`
    name: str
    kind: LandmarkKind
    lat: float
    lng: float


UNIVERSITIES: tuple[Landmark, ...] = (
    Landmark("du", "University of Dhaka", LandmarkKind.UNIVERSITY, 23.7340, 90.3929),
    Landmark("buet", "Bangladesh University of Engineering & Technology (BUET)", LandmarkKind.UNIVERSITY, 23.7265, 90.3925),
    Landmark("dhaka_college", "Dhaka College", LandmarkKind.UNIVERSITY, 23.7389, 90.3846),
    Landmark("nsu", "North South University", LandmarkKind.UNIVERSITY, 23.8153, 90.4256),
    Landmark("brac", "BRAC University", LandmarkKind.UNIVERSITY, 23.7726, 90.4246),
    Landmark("iub", "Independent University, Bangladesh (IUB)", LandmarkKind.UNIVERSITY, 23.8110, 90.4270),
    Landmark("ewu", "East West University", LandmarkKind.UNIVERSITY, 23.7690, 90.4260),
    Landmark("bubt", "Bangladesh University of Business & Technology (BUBT)", LandmarkKind.UNIVERSITY, 23.8223, 90.3644),
)

# MRT Line 6, south from Uttara toward Motijheel — the stretch that actually
# serves the areas rooms are listed in.
METRO_STATIONS: tuple[Landmark, ...] = (
    Landmark("mrt_uttara_north", "Uttara North MRT", LandmarkKind.METRO, 23.8690, 90.3690),
    Landmark("mrt_pallabi", "Pallabi MRT", LandmarkKind.METRO, 23.8250, 90.3648),
    Landmark("mrt_mirpur_11", "Mirpur 11 MRT", LandmarkKind.METRO, 23.8180, 90.3654),
    Landmark("mrt_mirpur_10", "Mirpur 10 MRT", LandmarkKind.METRO, 23.8069, 90.3687),
    Landmark("mrt_kazipara", "Kazipara MRT", LandmarkKind.METRO, 23.7975, 90.3720),
    Landmark("mrt_shewrapara", "Shewrapara MRT", LandmarkKind.METRO, 23.7889, 90.3745),
    Landmark("mrt_agargaon", "Agargaon MRT", LandmarkKind.METRO, 23.7779, 90.3800),
    Landmark("mrt_farmgate", "Farmgate MRT", LandmarkKind.METRO, 23.7580, 90.3894),
    Landmark("mrt_kawran_bazar", "Kawran Bazar MRT", LandmarkKind.METRO, 23.7510, 90.3930),
    Landmark("mrt_shahbagh", "Shahbagh MRT", LandmarkKind.METRO, 23.7389, 90.3958),
    Landmark("mrt_dhaka_university", "Dhaka University MRT", LandmarkKind.METRO, 23.7320, 90.3970),
    Landmark("mrt_motijheel", "Motijheel MRT", LandmarkKind.METRO, 23.7270, 90.4180),
)

ALL_LANDMARKS: tuple[Landmark, ...] = UNIVERSITIES + METRO_STATIONS

_BY_KEY: dict[str, Landmark] = {landmark.key: landmark for landmark in ALL_LANDMARKS}


def get_landmark(key: str) -> Landmark | None:
    """Resolve a landmark by its slug (`?near_landmark=` value), or None."""
    return _BY_KEY.get(key)
