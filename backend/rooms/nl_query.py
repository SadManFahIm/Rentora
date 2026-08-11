"""Natural-language query parsing for room search (Phase 11).

Turns free-text tenant language into structured filters. Handles the two
languages Rentora actually serves — Bangla and English — in one pass:

    "১০ হাজার এর মধ্যে uttara student room, জুলাই থেকে move-in"
        -> {budget_max: 10000, areas: ["Uttara"], room_type: None,
            months: ["July"], hints: [...]}

Bangla numerals and number words (হাজার/লাখ/কোটি), ৳/টাকা/tk/taka/ক/
thousand/k markers, area names (from the street gazetteer + Room.Area),
room-type and gender words, and month names (both scripts) are all
recognised. Everything the parser can't map is left alone — the query text
still goes to keyword/semantic search, so parsing only *adds* precision.

The result is exposed to the UI as chips ("Budget ≤ ৳10,000 · Uttara ·
move-in July") so tenants see exactly what was understood.
"""

from __future__ import annotations

import re

from .models import Room
from .streets import STREETS

# ---------------------------------------------------------------- numerals

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
# Bangla number *words* (দশ, বিশ…) — the digit path ("১০") is handled above.
_NUMBER_WORDS = {
    "এক": 1,
    "দুই": 2,
    "তিন": 3,
    "চার": 4,
    "পাঁচ": 5,
    "ছয়": 6,
    "ছয়": 6,
    "সাত": 7,
    "আট": 8,
    "নয়": 9,
    "নয়": 9,
    "দশ": 10,
    "এগারো": 11,
    "বারো": 12,
    "তেরো": 13,
    "চৌদ্দ": 14,
    "পনেরো": 15,
    "ষোল": 16,
    "ষোলো": 16,
    "সতেরো": 17,
    "আঠারো": 18,
    "উনিশ": 19,
    "বিশ": 20,
    "ত্রিশ": 30,
    "চল্লিশ": 40,
    "পঞ্চাশ": 50,
    "ষাট": 60,
    "সত্তর": 70,
    "আশি": 80,
    "নব্বই": 90,
    "শত": 100,
}
# Multipliers used in Bangla number words (and their English equivalents).
_MULTIPLIERS = {
    "হাজার": 1_000,
    "হাজারে": 1_000,
    "লাখ": 100_000,
    "লক্ষ": 100_000,
    "কোটি": 10_000_000,
    "থousand": 1_000,  # typo-tolerant ("thousand" misspelled)
    "thousand": 1_000,
    "k": 1_000,
    "k+": 1_000,
}
_BANGLA_MONTHS = {
    "জানুয়ারি": "January",
    "জানুয়ারী": "January",
    "ফেব্রুয়ারি": "February",
    "ফেব্রুয়ারী": "February",
    "মার্চ": "March",
    "এপ্রিল": "April",
    "মে": "May",
    "জুন": "June",
    "জুলাই": "July",
    "আগস্ট": "August",
    "সেপ্টেম্বর": "September",
    "অক্টোবর": "October",
    "নভেম্বর": "November",
    "ডিসেম্বর": "December",
}
_ENGLISH_MONTHS = {
    "january": "January",
    "february": "February",
    "march": "March",
    "april": "April",
    "may": "May",
    "june": "June",
    "july": "July",
    "august": "August",
    "september": "September",
    "october": "October",
    "november": "November",
    "december": "December",
}
_ROOM_TYPE_WORDS = {
    "single": Room.RoomType.SINGLE,
    "একক": Room.RoomType.SINGLE,
    "একটা": Room.RoomType.SINGLE,
    "shared": Room.RoomType.SHARED,
    "share": Room.RoomType.SHARED,
    "শেয়ার": Room.RoomType.SHARED,
    "শেয়ার": Room.RoomType.SHARED,
    "studio": Room.RoomType.STUDIO,
    "স্টুডিও": Room.RoomType.STUDIO,
}
_GENDER_WORDS = {
    "male": "male",
    "ছেলে": "male",
    "ভদ্রলোক": "male",
    "পুরুষ": "male",
    "female": "female",
    "মেয়ে": "female",
    "মেয়ে": "female",
    "মহিলা": "female",
    "নারী": "female",
}

# Area names the parser can recognise: Room.Area choices + gazetteer areas.
_AREA_ALIASES: dict[str, str] = {}
for value, label in Room.Area.choices:
    _AREA_ALIASES[value.lower()] = value
    _AREA_ALIASES[label.lower()] = value
for street in STREETS:
    if street.kind == "area":
        _AREA_ALIASES[street.name.lower()] = street.name
        for alias in street.aliases:
            _AREA_ALIASES[alias.lower()] = street.name


def normalize_bangla(text: str) -> str:
    """Bangla digits -> ASCII digits so number parsing is script-agnostic."""
    return text.translate(_BANGLA_DIGITS)


def parse_bangla_number(token: str) -> int | None:
    """Parse a possibly-Bangla number token like '১০', '10', '১২,৫০০', '10k'."""
    token = normalize_bangla(token.strip().replace(",", "")).lower()
    if not token:
        return None
    # "10k" -> 10000
    for word, mult in (("k", 1_000),):
        if token.endswith(word) and token[:-1].isdigit():
            return int(token[:-1]) * mult
    # Pure number
    if token.isdigit():
        return int(token)
    return None


def _parse_number_with_unit(text: str) -> int | None:
    """Parse '১০ হাজার', 'দশ হাজার', '12 thousand', '12000' (optional currency)."""
    t = re.sub(r"^[৳tkটাকাঃ ]+", "", normalize_bangla(text).lower().strip())
    # Bangla number words: "দশ হাজার" -> 10000, "বিশ হাজার" -> 20000.
    word_match = re.match(r"^([\u0980-\u09ff]+)\s*(হাজার|লাখ|লক্ষ|কোটি|thousand)?", t)
    if word_match:
        word = word_match.group(1)
        if word in _NUMBER_WORDS:
            value = _NUMBER_WORDS[word]
            mult = word_match.group(2)
            if mult:
                value *= _MULTIPLIERS.get(mult, 1_000)
            return value
    # Digit path: "১০ হাজার", "12 thousand", "12000".
    match = re.match(r"^([\d,]+)\s*([\d,]*)\s*(হাজার|লাখ|কোটি|thousand|k)?", t)
    if not match:
        return None
    number_part = (match.group(1) + (match.group(2) or "")).replace(",", "")
    if not number_part.isdigit():
        return None
    value = int(number_part)
    mult = match.group(3)
    if mult:
        value *= _MULTIPLIERS.get(mult, 1_000)
    return value


def parse_nl_query(text: str) -> dict:
    """Parse free text into structured filters + human-readable hints.

    Returns a dict with keys: budget_max, areas, room_type, gender, months,
    hints — each absent value None/[] (never raises).
    """
    if not text or not text.strip():
        return {
            "budget_max": None,
            "areas": [],
            "room_type": None,
            "gender": None,
            "months": [],
            "hints": [],
        }

    tokens = re.findall(r"\S+", text)
    result: dict = {
        "budget_max": None,
        "areas": [],
        "room_type": None,
        "gender": None,
        "months": [],
        "hints": [],
    }

    # --- budget: scan for "<number> <unit>" / "৳<number>" / "<number>k" ---
    for i, token in enumerate(tokens):
        joined = " ".join(tokens[i : i + 2])
        # "১০ হাজার", "12 thousand", "৳12000", "12000"
        value = _parse_number_with_unit(joined)
        if value is None:
            value = parse_bangla_number(token)
        if value and value >= 1000:  # ignore tiny numbers (room numbers, road 7…)
            # Only treat as budget if currency-marked or large (rents are 1k+)
            has_currency = any(m in token.lower() for m in ("৳", "tk", "taka", "টাকা"))
            if has_currency or value >= 2000:
                result["budget_max"] = value
                break

    # --- areas / room type / gender / months over the whole text ---
    lowered = normalize_bangla(text).lower()
    for alias, area in _AREA_ALIASES.items():
        if alias in lowered and area not in result["areas"]:
            result["areas"].append(area)
    for word, rtype in _ROOM_TYPE_WORDS.items():
        if word in lowered:
            result["room_type"] = rtype
    for word, gender in _GENDER_WORDS.items():
        if word in lowered:
            result["gender"] = gender
    for word, month in {**_BANGLA_MONTHS, **_ENGLISH_MONTHS}.items():
        if word in lowered and month not in result["months"]:
            result["months"].append(month)

    # --- human-readable chips ---
    if result["budget_max"]:
        result["hints"].append(f"Budget ≤ ৳{result['budget_max']:,}")
    if result["areas"]:
        result["hints"].append(" / ".join(result["areas"]))
    if result["room_type"]:
        result["hints"].append(result["room_type"])
    if result["gender"]:
        result["hints"].append(result["gender"] + " only")
    if result["months"]:
        result["hints"].append("move-in " + " / ".join(result["months"]))
    if not result["hints"]:
        result["hints"].append("keyword search")

    return result
