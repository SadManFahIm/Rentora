"""Canonical Dhaka area aliases + typo-tolerant resolution (Phase 11+).

Tenants search for places in three scripts and countless spellings —
``ধানমন্ডি``, ``Dhanmondi``, ``Dhanmondhi``, ``Dhanmondi 27`` all mean the
same area. This module is the single source of truth for that mapping:

- **Canonical** area names are the ``Room.Area`` choices (``"Dhanmondi"``,
  ``"Mirpur"``, …), so a resolved alias can be used directly as an
  ``area__in=`` filter.
- **Aliases** are curated per area: English, Bangla, Banglish, common typos
  (``dhanmondhi``, ``mirpore``), and street/sector forms (``mirpur 10``,
  ``ধানমন্ডি ২৭``). Street-level areas from ``streets.py`` are folded in so
  the map gazetteer and the search parser agree on place names.
- **Resolution** is exact-first, fuzzy-second: a whole-query substring pass
  catches ``"ধানমন্ডি ২৭"``; a bounded fuzzy pass (Python ``difflib`` over
  the small alias gazetteer — a few hundred tokens, sub-millisecond) catches
  same-script typos like ``"Mirpore"``. No heavy deps, no DB round-trips.

Everything downstream (``nl_query``, the smart-search view path) consumes
``ALIAS_TO_CANONICAL`` / ``find_areas_in_text`` instead of hand-rolled area
tables, so aliases live in exactly one place.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from .models import Room
from .streets import STREETS

# Lowercase + Bangla digits -> ASCII digits + script-normalized form of a
# place-name term ("ধানমন্ডি ২৭" -> "ধানমন্ডি 27"). Bangla consonant
# variants (ণ/ন, ড/ড়, য়/য…) are intentionally NOT collapsed here — those
# are handled by listing the common variants as explicit aliases below,
# which is safer than aggressive transliteration.
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_STRIP_RE = re.compile(r"[^\w\u0980-\u09ff ]+", re.UNICODE)


def normalize(text: str) -> str:
    """Lowercase, Bangla digits -> ASCII, punctuation -> spaces, collapse."""
    text = unicodedata.normalize("NFC", text or "").translate(_BANGLA_DIGITS).lower()
    text = text.replace("-", " ").replace("/", " ")
    text = _STRIP_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# Hand-curated aliases per canonical Room.Area, on top of what Room.Area /
# streets.py already contribute. Keep entries in the same script family as
# the area (Bangla aliases for Bangla names, English for English) plus the
# common mixed/banglish spellings people actually type.
_HAND_ALIASES: dict[str, set[str]] = {
    "Dhanmondi": {
        "dhanmondhi",
        "dhanmondie",
        "ধানমন্ডি",
        "ধানমণ্ডি",
        "ধানমোন্ডি",
        "ধানমোণ্ডি",
        "ধানমন্ডি ২৭",
        "ধানমণ্ডি ২৭",
        "ধানমন্ডি 27",
        "dhanmondi 27",
        "dhanmondi-27",
        "dhanmondi road 27",
        "dhaka dhanmondi",
    },
    "Mirpur": {
        "mirpore",
        "mirpur 10",
        "mirpur 11",
        "mirpur-10",
        "mirpur-11",
        "mirpur doha",
        "মিরপুর",
        "মিরপূর",
        "মিরপুর ১০",
        "মিরপুর ১০ নম্বর",
        "মিরপুর 10",
    },
    "Gulshan": {
        "gulsan",
        "gulshan 1",
        "gulshan 2",
        "gulshan circle 1",
        "gulshan circle 2",
        "গুলশান",
        "গুলশান ১",
        "গুলশান ২",
        "গুলশান 1",
        "গুলশান 2",
    },
    "Banani": {
        "banani 11",
        "banani road 11",
        "বনানী",
        "বানানী",
        "বনানি",
    },
    "Uttara": {
        "uttara sector 3",
        "uttara sector 7",
        "uttara sector 10",
        "uttara sector 11",
        "uttara sector 12",
        "uttara sector 13",
        "uttara sector 14",
        "uttra",
        "উত্তরা",
        "উত্তরা সেক্টর ১০",
        "উত্তরা সেক্টর 10",
        "উত্তরা ১০",
        "উত্তরা 10",
    },
    "Mohammadpur": {
        "মোহাম্মদপুর",
        "মহম্মদপুর",
        "মুহম্মদপুর",
        "mohammadpur 1",
        "mohammadpur 2",
        "mohammadpore",
    },
    "Azimpur": {"আজিমপুর", "azimpur 1", "azimpur 2"},
    "Tejgaon": {
        "tejgaon industrial",
        "তেজগাঁও",
        "তেজগাঁওথানা",
        "tejgawn",
    },
    "Badda": {"বাড্ডা", "badda 1", "badda 2"},
    "Rampura": {"রামপুরা", "রামপুড়া"},
    "Banasree": {"বনশ্রী", "banasri", "banasre"},
    "Khilgaon": {"খিলগাঁও", "khilgawn", "khilgoan"},
    "Motijheel": {
        "motijheel c/a",
        "motijheel commercial area",
        "মতিঝিল",
        "মতিঝিল সি/এ",
        "motijheel 1",
    },
    "Old Dhaka": {
        "old dhaka",
        "purana dhaka",
        "bangshal",
        "পুরান ঢাকা",
        "পুরানো ঢাকা",
        "পুরানা ঢাকা",
        "puran dhaka",
    },
    "Bashundhara": {
        "bashundhara r/a",
        "bashundhara residential area",
        "বসুন্ধরা",
        "বসুন্ধরা আবাসিক এলাকা",
        "bashundhara block a",
        "bashundhara block c",
    },
    "Lalmatia": {"লালমাটিয়া", "লালমাটিয়া", "lalmatiya"},
    "Shyamoli": {"শ্যামলী", "শ্যামলি", "shyamoly"},
    "Savar": {"savar epz", "সাভার", "সাভার ইপিজেড", "savar bus stand"},
    "Keraniganj": {"কেরানীগঞ্জ", "কেরানিগঞ্জ", "keranigong", "keraniganj"},
    "Tongi": {"tongi bazar", "টঙ্গী", "টঙ্গি", "tongi station"},
}


def _build_alias_map() -> dict[str, tuple[str, ...]]:
    """canonical area -> all aliases (canonical forms, streets, hand-added)."""
    aliases: dict[str, set[str]] = {}

    # Room.Area choices: canonical value + label (same thing here) are always
    # aliases of themselves, so a bare "dhanmondi" resolves.
    for value, label in Room.Area.choices:
        aliases.setdefault(value, set()).update({value.lower(), label.lower()})

    # Street-level areas from the map gazetteer — same canonical name, extra
    # searchable aliases (e.g. "Motijheel C/A", "পুরান ঢাকা").
    for street in STREETS:
        if street.kind != "area":
            continue
        aliases.setdefault(street.name, set()).add(street.name.lower())
        for alias in street.aliases:
            aliases[street.name].add(alias.lower())

    for canonical, extra in _HAND_ALIASES.items():
        aliases.setdefault(canonical, set()).update(a.lower() for a in extra)

    # Drop collisions: if the same alias maps to two canonical names (e.g. a
    # street area name that duplicates a Room.Area), keep the canonical that
    # appears first in Room.Area order — Room.Area wins over streets.
    first_seen: dict[str, str] = {}
    canonical_order = [v for v, _ in Room.Area.choices] + [
        s.name for s in STREETS if s.kind == "area"
    ]
    for canonical in canonical_order:
        if canonical not in aliases:
            continue
        for alias in aliases[canonical]:
            first_seen.setdefault(alias, canonical)
    # Rebuild as {canonical: (aliases, ...)} with only winning aliases.
    result: dict[str, set[str]] = {c: set() for c in canonical_order if c in aliases}
    for alias, canonical in first_seen.items():
        result[canonical].add(alias)
    return {c: tuple(sorted(s)) for c, s in result.items() if s}


AREA_ALIASES: dict[str, tuple[str, ...]] = _build_alias_map()

# Lowercased alias -> canonical area (the fast exact lookup table).
ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical for canonical, aliases in AREA_ALIASES.items() for alias in aliases
}

# All aliases, longest first, for whole-text matching (longest match wins —
# "dhanmondi 27" beats "dhanmondi").
_ALL_ALIASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((alias, canonical) for canonical, aliases in AREA_ALIASES.items() for alias in aliases),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)

# Fuzzy-matching cutoff over the alias gazetteer. High enough that "mirpore"
# -> "mirpur" still passes but a random word ("room") can't glom onto any area.
_FUZZY_CUTOFF = 0.72
# Skip fuzzy matching on very short terms ("ok", "du") — too much noise.
_MIN_FUZZY_LEN = 4


def resolve_area(text: str) -> str | None:
    """Exact resolution: is ``text`` (or an alias inside it) an area?

    Returns the canonical ``Room.Area`` value, or None. Prefers the longest
    matching alias inside the text, so "dhanmondi 27" resolves to Dhanmondi
    even though "dhanmondi" also appears as a substring.
    """
    normalized = normalize(text)
    if not normalized:
        return None
    # Whole normalized text as an alias first (e.g. "mirpur 10").
    if normalized in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[normalized]
    for alias, canonical in _ALL_ALIASES:
        if len(alias) >= 4 and alias in normalized:
            return canonical
    return None


def fuzzy_resolve_area(term: str) -> str | None:
    """Typo-tolerant resolution of a single term (same-script typos)."""
    normalized = normalize(term)
    if len(normalized) < _MIN_FUZZY_LEN:
        return None
    exact = ALIAS_TO_CANONICAL.get(normalized)
    if exact:
        return exact
    close = difflib.get_close_matches(
        normalized, list(ALIAS_TO_CANONICAL), n=1, cutoff=_FUZZY_CUTOFF
    )
    if close:
        return ALIAS_TO_CANONICAL[close[0]]
    return None


def find_areas_in_text(text: str, fuzzy: bool = False) -> list[str]:
    """Canonical areas mentioned anywhere in ``text``, in gazetteer order.

    Runs the exact longest-alias pass over the whole text first, then — when
    ``fuzzy`` is on — a bounded per-token fuzzy pass for same-script typos
    (``mirpore``, ``মিরপূর``). Returns canonical ``Room.Area`` values; street
    areas that aren't Room.Area choices (e.g. ``Farmgate``) are included so
    the parser's behavior is unchanged from the pre-alias version.
    """
    normalized = normalize(text)
    if not normalized:
        return []

    found: list[str] = []
    seen: set[str] = set()

    for alias, canonical in _ALL_ALIASES:
        if len(alias) >= 4 and alias in normalized and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)

    if fuzzy and not found:
        for token in re.findall(r"[\w\u0980-\u09ff]+", normalized):
            if len(token) < _MIN_FUZZY_LEN:
                continue
            resolved = fuzzy_resolve_area(token)
            if resolved and resolved not in seen:
                found.append(resolved)
                seen.add(resolved)

    return found
