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
    HOSPITAL = "hospital"
    MARKET = "market"
    PARK = "park"
    MOSQUE = "mosque"
    BUS_TERMINAL = "bus_terminal"


@dataclass(frozen=True)
class Landmark:
    key: str  # stable slug — the value accepted by `?near_landmark=`
    name: str
    kind: LandmarkKind
    lat: float
    lng: float


UNIVERSITIES: tuple[Landmark, ...] = (
    Landmark("du", "University of Dhaka", LandmarkKind.UNIVERSITY, 23.7340, 90.3929),
    Landmark(
        "buet",
        "Bangladesh University of Engineering & Technology (BUET)",
        LandmarkKind.UNIVERSITY,
        23.7265,
        90.3925,
    ),
    Landmark("dhaka_college", "Dhaka College", LandmarkKind.UNIVERSITY, 23.7389, 90.3846),
    Landmark("nsu", "North South University", LandmarkKind.UNIVERSITY, 23.8153, 90.4256),
    Landmark("brac", "BRAC University", LandmarkKind.UNIVERSITY, 23.7726, 90.4246),
    Landmark(
        "iub", "Independent University, Bangladesh (IUB)", LandmarkKind.UNIVERSITY, 23.8110, 90.4270
    ),
    Landmark("ewu", "East West University", LandmarkKind.UNIVERSITY, 23.7690, 90.4260),
    Landmark(
        "bubt",
        "Bangladesh University of Business & Technology (BUBT)",
        LandmarkKind.UNIVERSITY,
        23.8223,
        90.3644,
    ),
    Landmark(
        "jagannath",
        "Jagannath University",
        LandmarkKind.UNIVERSITY,
        23.7098,
        90.4120,
    ),
    Landmark("dmc", "Dhaka Medical College", LandmarkKind.UNIVERSITY, 23.7260, 90.3940),
    Landmark(
        "sau",
        "Sher-e-Bangla Agricultural University",
        LandmarkKind.UNIVERSITY,
        23.7760,
        90.3710,
    ),
    Landmark(
        "aust",
        "Ahsanullah University of Science & Technology",
        LandmarkKind.UNIVERSITY,
        23.7820,
        90.4130,
    ),
    Landmark(
        "diu",
        "Daffodil International University",
        LandmarkKind.UNIVERSITY,
        23.7520,
        90.3760,
    ),
    Landmark(
        "stamford",
        "Stamford University Bangladesh",
        LandmarkKind.UNIVERSITY,
        23.7520,
        90.4110,
    ),
    Landmark(
        "uiu",
        "United International University",
        LandmarkKind.UNIVERSITY,
        23.7610,
        90.3910,
    ),
    Landmark(
        "miu",
        "Manarat International University",
        LandmarkKind.UNIVERSITY,
        23.8300,
        90.4250,
    ),
    Landmark(
        "daffodil_uttara",
        "Daffodil International University (Uttara)",
        LandmarkKind.UNIVERSITY,
        23.8750,
        90.3800,
    ),
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

# ---- everyday places (Phase 7 v3) ----
# Real, well-known Dhaka hospitals, markets, parks, mosques and bus
# terminals — the places a tenant actually asks "how far to X" about.
# Same approximate-coordinates policy as universities/metro.
HOSPITALS: tuple[Landmark, ...] = (
    Landmark("dmch", "Dhaka Medical College Hospital", LandmarkKind.HOSPITAL, 23.7260, 90.3940),
    Landmark("bsmmu", "BSMMU (PG Hospital)", LandmarkKind.HOSPITAL, 23.7380, 90.3950),
    Landmark("square_hospital", "Square Hospital", LandmarkKind.HOSPITAL, 23.7490, 90.3900),
    Landmark(
        "apollo_evercare", "Apollo (Evercare) Hospital", LandmarkKind.HOSPITAL, 23.7900, 90.4080
    ),
    Landmark(
        "mitford_hospital",
        "Sir Salimullah Medical College (Mitford)",
        LandmarkKind.HOSPITAL,
        23.7060,
        90.4160,
    ),
    Landmark(
        "shyamoli_chest",
        "National Chest Hospital (Shyamoli)",
        LandmarkKind.HOSPITAL,
        23.7730,
        90.3620,
    ),
    Landmark("kurmitola_gh", "Kurmitola General Hospital", LandmarkKind.HOSPITAL, 23.8260, 90.4070),
)

MARKETS: tuple[Landmark, ...] = (
    Landmark("new_market", "New Market", LandmarkKind.MARKET, 23.7310, 90.3810),
    Landmark("kawran_bazar_market", "Kawran Bazar", LandmarkKind.MARKET, 23.7500, 90.3920),
    Landmark("bashundhara_city", "Bashundhara City Mall", LandmarkKind.MARKET, 23.7500, 90.3960),
    Landmark("jamuna_future_park", "Jamuna Future Park", LandmarkKind.MARKET, 23.8130, 90.4290),
    Landmark("gulshan_market", "Gulshan Market (DCC)", LandmarkKind.MARKET, 23.7900, 90.4140),
    Landmark("mirpur_1_market", "Mirpur 1 New Market", LandmarkKind.MARKET, 23.8060, 90.3640),
    Landmark(
        "utara_sector3_market", "Uttara Sector 3 Market", LandmarkKind.MARKET, 23.8680, 90.3890
    ),
)

PARKS: tuple[Landmark, ...] = (
    Landmark("ramna_park", "Ramna Park", LandmarkKind.PARK, 23.7360, 90.4000),
    Landmark("suhrawardy_udyan", "Suhrawardy Udyan", LandmarkKind.PARK, 23.7340, 90.3950),
    Landmark("baldha_garden", "Baldha Garden", LandmarkKind.PARK, 23.7240, 90.4010),
    Landmark("dhaka_zoo", "Dhaka Zoo (Mirpur)", LandmarkKind.PARK, 23.8060, 90.3440),
    Landmark("dhanmondi_lake", "Dhanmondi Lake Park", LandmarkKind.PARK, 23.7440, 90.3730),
    Landmark("hatirjheel_park", "Hatirjheel", LandmarkKind.PARK, 23.7760, 90.4090),
    Landmark("uttara_park", "Uttara Sector 7 Park", LandmarkKind.PARK, 23.8670, 90.3760),
)

MOSQUES: tuple[Landmark, ...] = (
    Landmark(
        "baitul_mukarram", "Baitul Mukarram National Mosque", LandmarkKind.MOSQUE, 23.7290, 90.4120
    ),
    Landmark("star_mosque", "Star Mosque (Tara Masjid)", LandmarkKind.MOSQUE, 23.7190, 90.4010),
    Landmark("lalbagh_fort_mosque", "Lalbagh Fort", LandmarkKind.MOSQUE, 23.7190, 90.3880),
    Landmark("kakrail_mosque", "Kakrail Mosque", LandmarkKind.MOSQUE, 23.7390, 90.3970),
    Landmark("chawkbazar_shahi", "Chawkbazar Shahi Mosque", LandmarkKind.MOSQUE, 23.7130, 90.4080),
    Landmark("gulshan_mosque", "Gulshan Azad Mosque", LandmarkKind.MOSQUE, 23.7920, 90.4170),
    Landmark("mirpur_mosque", "Mirpur 10 Central Mosque", LandmarkKind.MOSQUE, 23.8070, 90.3690),
)

BUS_TERMINALS: tuple[Landmark, ...] = (
    Landmark("gabtoli", "Gabtoli Bus Terminal", LandmarkKind.BUS_TERMINAL, 23.7780, 90.3330),
    Landmark("saidabad", "Saidabad Bus Terminal", LandmarkKind.BUS_TERMINAL, 23.7050, 90.4260),
    Landmark(
        "mohakhali_terminal", "Mohakhali Bus Terminal", LandmarkKind.BUS_TERMINAL, 23.7750, 90.4030
    ),
    Landmark(
        "motijheel_terminal", "Motijheel Bus Stand", LandmarkKind.BUS_TERMINAL, 23.7280, 90.4170
    ),
    Landmark("kalabagan_stand", "Kalabagan Bus Stand", LandmarkKind.BUS_TERMINAL, 23.7490, 90.3780),
    Landmark(
        "uttara_terminal",
        "Uttara (Abdullahpur) Bus Terminal",
        LandmarkKind.BUS_TERMINAL,
        23.8900,
        90.3860,
    ),
)

ALL_LANDMARKS: tuple[Landmark, ...] = (
    UNIVERSITIES + METRO_STATIONS + HOSPITALS + MARKETS + PARKS + MOSQUES + BUS_TERMINALS
)

_BY_KEY: dict[str, Landmark] = {landmark.key: landmark for landmark in ALL_LANDMARKS}


def get_landmark(key: str) -> Landmark | None:
    """Resolve a landmark by its slug (`?near_landmark=` value), or None."""
    return _BY_KEY.get(key)
