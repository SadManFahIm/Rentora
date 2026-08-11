"""Curated Dhaka street / area gazetteer for map search (Phase 7).

A small, hand-maintained index of the roads, neighbourhoods and districts a
tenant actually searches for on a map ("Mirpur Road", "Gulshan Avenue",
"Dhanmondi"). Coordinates are approximate real-world positions — good enough
to fly the map to the right neighbourhood and seed a radius search.

Hardcoded on purpose, like the landmarks: the set is small and stable, so it
lives in code rather than a DB table. If street data ever needs to be
exhaustive (every lane in Dhaka), swap this module for a geocoding provider
(Nominatim/Photon) behind the same ``search_streets`` interface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Street:
    key: str  # stable slug — the suggestion's identifier
    name: str  # display label, e.g. "Mirpur Road"
    kind: str  # "street" | "area"
    lat: float
    lng: float
    # Extra searchable terms ("Dhanmondi 27", "C/A" for commercial area).
    aliases: tuple[str, ...] = ()


STREETS: tuple[Street, ...] = (
    # ---- major roads / avenues ----
    Street("mirpur_road", "Mirpur Road", "street", 23.7830, 90.3730, ("Mirpur Rd",)),
    Street("gulshan_avenue", "Gulshan Avenue", "street", 23.7895, 90.4120),
    Street(
        "banani_road_11",
        "Road 11, Banani",
        "street",
        23.7937,
        90.4066,
        ("Banani Rd 11",),
    ),
    Street("airport_road", "Airport Road", "street", 23.8200, 90.4000),
    Street(
        "new_elephant_road",
        "New Elephant Road",
        "street",
        23.7410,
        90.3815,
        ("Elephant Road",),
    ),
    Street("green_road", "Green Road", "street", 23.7540, 90.3825),
    Street(
        "satmasjid_road",
        "Satmasjid Road",
        "street",
        23.7480,
        90.3715,
        ("Dhanmondi 8/A",),
    ),
    Street(
        "kazi_nazrul_islam_avenue",
        "Kazi Nazrul Islam Avenue",
        "street",
        23.7550,
        90.3880,
    ),
    Street("bijoy_sarani", "Bijoy Sarani", "street", 23.7670, 90.3930),
    Street("progati_sarani", "Progati Sarani", "street", 23.7750, 90.4170),
    Street("manik_mia_avenue", "Manik Mia Avenue", "street", 23.7690, 90.3870),
    Street("asad_avenue", "Asad Avenue", "street", 23.7570, 90.3690),
    Street(
        "central_road",
        "Central Road, Dhanmondi",
        "street",
        23.7455,
        90.3755,
        ("Dhanmondi Road 7",),
    ),
    Street(
        "dhanmondi_road_27",
        "Road 27, Dhanmondi",
        "street",
        23.7434,
        90.3773,
        ("Dhanmondi 27",),
    ),
    Street("elephant_road", "Elephant Road", "street", 23.7440, 90.3805),
    # ---- commercial hubs ----
    Street("farmgate", "Farmgate", "area", 23.7580, 90.3894),
    Street("motijheel", "Motijheel Commercial Area", "area", 23.7330, 90.4170, ("Motijheel C/A",)),
    Street("shahbagh", "Shahbagh", "area", 23.7380, 90.3960),
    Street("tejgaon", "Tejgaon", "area", 23.7600, 90.4000),
    Street("mohakhali", "Mohakhali", "area", 23.7750, 90.4030),
    Street("nayapaltan", "Nayapaltan", "area", 23.7410, 90.4020),
    Street("eskaton", "Eskaton", "area", 23.7430, 90.3970),
    Street("malibagh", "Malibagh", "area", 23.7540, 90.4050),
    Street("moghbazar", "Moghbazar", "area", 23.7540, 90.3980),
    Street("rampura", "Rampura", "area", 23.7650, 90.4270),
    Street("badda", "Badda", "area", 23.7740, 90.4230),
    # ---- residential areas ----
    Street("dhanmondi", "Dhanmondi", "area", 23.7461, 90.3742),
    Street("mirpur", "Mirpur", "area", 23.8223, 90.3654),
    Street("gulshan", "Gulshan", "area", 23.7808, 90.4152),
    Street("banani", "Banani", "area", 23.7937, 90.4066),
    Street("mohammadpur", "Mohammadpur", "area", 23.7623, 90.3588),
    Street("azimpur", "Azimpur", "area", 23.7226, 90.3874),
    Street("lalmatia", "Lalmatia", "area", 23.7600, 90.3670),
    Street("shyamoli", "Shyamoli", "area", 23.7706, 90.3619),
    Street("uttara", "Uttara", "area", 23.8759, 90.3795, ("Uttara Sector 3", "Uttara Sector 7")),
    Street("banasree", "Banasree", "area", 23.7700, 90.4320),
    Street("basabo", "Basabo", "area", 23.7550, 90.4300),
    Street("kuril", "Kuril", "area", 23.8180, 90.4230, ("Kuril Flyover",)),
    Street("old_dhaka", "Old Dhaka", "area", 23.7100, 90.4120, ("Bangshal",)),
    Street("bashundhara", "Bashundhara", "area", 23.8150, 90.4270, ("Bashundhara R/A",)),
    Street("savar", "Savar", "area", 23.8583, 90.2668, ("Savar EPZ",)),
    Street("keraniganj", "Keraniganj", "area", 23.6800, 90.3600),
    Street("tongi", "Tongi", "area", 23.8900, 90.4050, ("Tongi Bazar",)),
    # ---- more roads / lanes ----
    Street(
        "panthapath",
        "Panthapath",
        "street",
        23.7510,
        90.3875,
        ("Pan Pacific Panthapath",),
    ),
    Street("bailey_road", "Bailey Road", "street", 23.7430, 90.3940),
    Street("hatirjheel", "Hatirjheel", "area", 23.7760, 90.4090, ("Hatirjheel Lake",)),
    Street(
        "dhaka_mymensingh_road",
        "Dhaka-Mymensingh Road",
        "street",
        23.8300,
        90.3830,
        ("N3",),
    ),
    Street(
        "tongi_diversion_road",
        "Tongi Diversion Road",
        "street",
        23.8550,
        90.3870,
        ("Dhaka-Tongi Road",),
    ),
    Street("mouchak", "Mouchak", "area", 23.7600, 90.4020),
    Street("kakrail", "Kakrail", "area", 23.7440, 90.4000),
    Street("segunbagicha", "Segunbagicha", "area", 23.7410, 90.4010),
    Street("kawran_bazar", "Kawran Bazar", "area", 23.7520, 90.3920),
    Street("nikunja", "Nikunja", "area", 23.8350, 90.4130, ("Nikunja 2",)),
    Street("khilkhet", "Khilkhet", "area", 23.8280, 90.4190),
    Street("dakshinkhan", "Dakshinkhan", "area", 23.8750, 90.3840),
    Street(
        "badda_link_road",
        "Badda Link Road",
        "street",
        23.7770,
        90.4240,
        ("Link Road Badda",),
    ),
    Street("khilgaon_flyover", "Khilgaon Flyover", "street", 23.7470, 90.4210),
    Street("malibagh_railgate", "Malibagh Railgate", "area", 23.7530, 90.4030),
    Street("rampura_bridge", "Rampura Bridge", "street", 23.7660, 90.4300),
    Street("sobanbagh", "Sobhanbagh", "area", 23.7460, 90.3660),
    Street("asad_gate", "Asad Gate", "area", 23.7620, 90.3670),
    Street("agargaon", "Agargaon", "area", 23.7770, 90.3810, ("Agargaon Taltola",)),
    Street("shewrapara", "Shewrapara", "area", 23.7890, 90.3740),
    Street("kallyanpur", "Kallyanpur", "area", 23.7950, 90.3500),
    Street("darussalam", "Darussalam", "area", 23.8020, 90.3570),
    Street("monipur", "Monipur", "area", 23.8300, 90.3600),
    Street("banasree_main_road", "Banasree Main Road", "street", 23.7710, 90.4350),
    Street("gulshan_circle_1", "Gulshan 1 Circle", "area", 23.7910, 90.4130, ("Gulshan 1",)),
    Street("gulshan_circle_2", "Gulshan 2 Circle", "area", 23.7860, 90.4150, ("Gulshan 2",)),
    Street("uttara_sector_10", "Uttara Sector 10", "area", 23.8690, 90.3990),
    Street("uttara_sector_12", "Uttara Sector 12", "area", 23.8650, 90.4090),
    Street("uttara_sector_14", "Uttara Sector 14", "area", 23.8600, 90.3900),
    Street("jashimuddin_avenue", "Jashimuddin Avenue", "street", 23.8050, 90.4050),
    Street("pragati_avenue", "Pragati Avenue", "street", 23.7730, 90.4200),
    Street(
        "bir_uttam_mir_shawkat_sarani", "Bir Uttam Mir Shawkat Sarani", "street", 23.8060, 90.3980
    ),
    Street("siddheswari", "Siddheswari", "area", 23.7520, 90.4110),
    Street("rajarbagh", "Rajarbagh", "area", 23.7400, 90.4110),
    Street("mogbazar_mor", "Moghbazar Mor", "area", 23.7540, 90.4000, ("Moghbazar",)),
)


_BY_NAME: dict[str, Street] = {street.name: street for street in STREETS}


def area_center(area_name: str) -> tuple[float, float] | None:
    """Center coordinates for a district/area name, if the gazetteer knows it.

    Used to attach a fly-to point to each row of the room-count summary — so
    an "areas in view" chip knows where to take the map when clicked.
    """
    street = _BY_NAME.get(area_name)
    if street is None:
        return None
    return (street.lat, street.lng)


def search_streets(query: str, limit: int = 8) -> list[Street]:
    """Ranked street/area suggestions for an autocomplete query.

    Matching is a simple case-insensitive substring pass over the display
    name and aliases; prefix matches outrank contains-matches, and streets
    beat areas (a specific road is more actionable than a whole district).
    Returns at most ``limit`` results, best-first.
    """
    q = query.strip().lower()
    if not q:
        return []

    scored: list[tuple[int, Street]] = []
    for street in STREETS:
        candidates = (street.name, *street.aliases)
        # Score the best matching candidate (not just the first), so an alias
        # that is a prefix match outranks a display name that merely contains
        # the query — e.g. "Uttara" should hit the aliased entry cleanly.
        best = None
        for text in candidates:
            lower = text.lower()
            if lower.startswith(q):
                best = 0 if street.kind == "street" else 1
                break
            if q in lower and best is None:
                best = 2 if street.kind == "street" else 3
        if best is not None:
            scored.append((best, street))

    scored.sort(key=lambda pair: (pair[0], pair[1].name.lower()))
    return [street for _, street in scored[:limit]]
