"""Chat live translation EN⇄BN (Phase 15 — B1).

A deterministic, self-hosted phrase-table translator for the everyday
vocabulary of a room-rental conversation, with an optional ``http`` gateway
for full machine translation (``CHAT_TRANSLATE_PROVIDER=http``).

Honesty contract (same as the vision module): this is a *phrase* translator,
not machine translation. It converts the sentences it can cover (>= half of
the words matched by a known bilingual phrase) and leaves everything else
untouched; every response reports ``quality`` (``full`` | ``phrase`` | ``none``)
so the UI never pretends an untranslated sentence was translated. The same
phrase core powers a safety-augmentation layer in ``safety.py`` — Bengali
payloads are normalized to English and re-scanned, so an English-only pattern
can still catch a Bengali scam message.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

# The Bangla script block (U+0980-U+09FF) includes the Bangla digits.
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
# Script letters (Latin + Bangla) used for the language-ratio test.
_SCRIPT_RE = re.compile(r"[A-Za-z\u0980-\u09FF]")
# A text is "Bangla" when at least this share of its script letters are Bangla.
_BENGALI_RATIO = 0.30
# A sentence is only phrase-translated when at least this share of its words
# is covered by known phrases — below that it stays untouched (honest, no
# half-translation). 0.30 keeps short filler-heavy sentences (what/is/the)
# translatable while leaving heavily-unknown sentences alone.
_MIN_COVERAGE = 0.30

_GATEWAY_TIMEOUT_SECONDS = 10

# Bangla <-> ASCII digit tables (Bangla uses its own digit glyphs).
_BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_ASCII_TO_BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

# Bilingual phrase table (English, Bangla). Matched longest-first. The
# safety-critical payment/impersonation vocabulary is deliberately included so
# the safety engine's cross-lingual scan (safety.detect_crosslingual) can
# normalize a Bengali scam payload into the English patterns' reach.
PHRASES: list[tuple[str, str]] = [
    # greetings / small talk
    ("hello", "হ্যালো"),
    ("hi", "হাই"),
    ("good morning", "শুভ সকাল"),
    ("good afternoon", "শুভ অপরাহ্ন"),
    ("good evening", "শুভ সন্ধ্যা"),
    ("thank you", "ধন্যবাদ"),
    ("thanks", "ধন্যবাদ"),
    ("please", "দয়া করে"),
    ("okay", "ঠিক আছে"),
    ("ok", "ঠিক আছে"),
    ("yes", "হ্যাঁ"),
    ("no", "না"),
    ("sorry", "দুঃখিত"),
    ("welcome", "স্বাগতম"),
    ("i am", "আমি"),
    ("brother", "ভাই"),
    ("sister", "আপু"),
    # rental vocabulary
    ("room", "রুম"),
    ("rooms", "রুম"),
    ("rent", "ভাড়া"),
    ("monthly rent", "মাসিক ভাড়া"),
    ("per month", "প্রতি মাসে"),
    ("per person", "প্রতি জনে"),
    ("deposit", "জমা"),
    ("security deposit", "সিকিউরিটি ডিপোজিট"),
    ("advance", "আগাম"),
    ("utilities", "ইউটিলিটি"),
    ("electricity", "বিদ্যুৎ"),
    ("water", "পানি"),
    ("gas", "গ্যাস"),
    ("internet", "ইন্টারনেট"),
    ("available", "আছে"),
    ("not available", "নেই"),
    ("visit", "দেখা"),
    ("viewing", "দেখা"),
    ("see the room", "রুম দেখতে"),
    ("location", "ঠিকানা"),
    ("address", "ঠিকানা"),
    ("area", "এলাকা"),
    ("floor", "তলা"),
    ("flat", "ফ্ল্যাট"),
    ("apartment", "অ্যাপার্টমেন্ট"),
    ("building", "বিল্ডিং"),
    ("bedroom", "বেডরুম"),
    ("bathroom", "বাথরুম"),
    ("kitchen", "রান্নাঘর"),
    ("balcony", "বারান্দা"),
    ("dining", "ডাইনিং"),
    ("lift", "লিফট"),
    ("furnished", "আসবাবসহ"),
    ("unfurnished", "আসবাব ছাড়া"),
    ("furniture", "আসবাবপত্র"),
    ("shared", "শেয়ার্ড"),
    ("separate", "আলাদা"),
    ("single", "একা"),
    ("family", "পরিবার"),
    ("bachelor", "ব্যাচেলর"),
    ("married", "পরিবার নিয়ে"),
    ("pet", "পোষা প্রাণী"),
    ("no pets", "পোষা প্রাণী নেই"),
    ("smoking", "ধূমপান"),
    ("contract", "চুক্তি"),
    ("agreement", "চুক্তিপত্র"),
    ("documents", "ডকুমেন্ট"),
    ("document", "ডকুমেন্ট"),
    ("nid", "এনআইডি"),
    ("nid card", "এনআইডি কার্ড"),
    ("copy", "কপি"),
    ("key", "চাবি"),
    ("owner", "মালিক"),
    ("landlord", "বাড়িওয়ালা"),
    ("tenant", "ভাড়াটিয়া"),
    ("student", "ছাত্র"),
    ("job holder", "চাকরিজীবী"),
    ("move in", "ওঠা"),
    ("move out", "ওঠে যাওয়া"),
    ("check in", "চেক ইন"),
    ("check out", "চেক আউট"),
    ("month", "মাস"),
    ("week", "সপ্তাহ"),
    ("today", "আজ"),
    ("tomorrow", "আগামীকাল"),
    ("yesterday", "গতকাল"),
    ("now", "এখন"),
    ("tonight", "আজ রাতে"),
    ("price", "দাম"),
    ("cost", "খরচ"),
    ("taka", "টাকা"),
    ("money", "টাকা"),
    ("bangladesh", "বাংলাদেশ"),
    ("dhaka", "ঢাকা"),
    ("mirpur", "মিরপুর"),
    ("uttara", "উত্তরা"),
    ("dhanmondi", "ধানমন্ডি"),
    ("gulshan", "গুলশান"),
    ("banani", "বনানী"),
    ("badda", "বাড্ডা"),
    ("mohakhali", "মহাখালী"),
    ("bashundhara", "বসুন্ধরা"),
    ("tejgaon", "তেজগাঁও"),
    ("mohammadpur", "মোহাম্মদপুর"),
    ("lalmatia", "লালমাটিয়া"),
    # safety-critical vocabulary (BN -> EN feeds the cross-lingual safety scan)
    ("bkash", "বিকাশ"),
    ("nagad", "নগদ"),
    ("rocket", "রকেট"),
    ("western union", "ওয়েস্টার্ন ইউনিয়ন"),
    ("western union", "পশ্চিম ইউনিয়ন"),
    ("moneygram", "মানিগ্রাম"),
    ("send money", "টাকা পাঠান"),
    ("send money", "টাকা পাঠাও"),
    ("payment", "পেমেন্ট"),
    ("pay", "পেমেন্ট"),
    ("transfer", "ট্রান্সফার"),
    ("advance fee", "আগাম টাকা"),
    ("booking fee", "বুকিং ফি"),
    ("processing fee", "প্রসেসিং ফি"),
    ("transfer fee", "ট্রান্সফার ফি"),
    ("clearance fee", "ক্লিয়ারেন্স ফি"),
    ("refund", "রিফান্ড"),
    ("number", "নম্বর"),
    ("otp", "ওটিপি"),
    ("password", "পাসওয়ার্ড"),
    ("pin", "পিন"),
    ("verification code", "ভেরিফিকেশন কোড"),
    ("verification", "ভেরিফিকেশন"),
    ("official", "অফিসিয়াল"),
    ("admin", "অ্যাডমিন"),
    ("support", "সাপোর্ট"),
    ("staff", "স্টাফ"),
    ("moderator", "মডারেটর"),
    ("rentora", "রেন্টোরা"),
    ("urgent", "জরুরি"),
    ("hurry", "ঝটপট"),
    ("immediately", "এখনই"),
    ("today only", "আজই"),
    ("last chance", "শেষ সুযোগ"),
    ("whatsapp", "হোয়াটসঅ্যাপ"),
    ("telegram", "টেলিগ্রাম"),
    ("call me", "আমাকে কল"),
    ("contact", "যোগাযোগ"),
    ("give me", "আমাকে দিন"),
    ("send me", "আমাকে পাঠান"),
    ("your name", "আপনার নাম"),
    ("my name", "আমার নাম"),
    ("name", "নাম"),
]


@dataclass
class TranslationResult:
    """One translation request's outcome.

    ``quality``:
    - ``full`` — produced by the configured ``http`` gateway (machine
      translation; the gateway is trusted for fluency),
    - ``phrase`` — the deterministic phrase core covered every translated
      sentence,
    - ``none`` — nothing could be translated; ``translated`` is the input.
    ``note`` is a short human-readable explanation of the outcome.
    """

    translated: str
    source_lang: str
    target_lang: str
    quality: str
    provider: str
    note: str


def detect_language(text: str) -> str:
    """``"bn"`` when at least :data:`_BENGALI_RATIO` of the script letters are
    Bangla, else ``"en"``. Empty/undetermined input counts as English."""
    if not text:
        return "en"
    script_chars = _SCRIPT_RE.findall(text)
    if not script_chars:
        return "en"
    bengali = sum(1 for ch in script_chars if _BENGALI_RE.match(ch))
    return "bn" if bengali / len(script_chars) >= _BENGALI_RATIO else "en"


def _phrase_index(lang: str) -> dict[int, list[tuple[str, str, re.Pattern]]]:
    """Phrases indexed by word count for longest-first matching: maps
    ``word_count -> [(source, target, compiled)]`` for the given source lang.

    English patterns use ``\\b`` word boundaries. Bengali cannot: many words
    end in vowel signs (U+0980-U+09FF marks) which Python's ``\\w`` does not
    treat as word characters, so ``\\b`` would never match them. Bengali
    patterns instead use explicit lookarounds asserting the neighbours are
    not Bengali script characters."""
    index: dict[int, list[tuple[str, str, re.Pattern]]] = {}
    for en, bn in PHRASES:
        src, dst = (en, bn) if lang == "en" else (bn, en)
        words = len(re.findall(r"\w+", src, re.UNICODE))
        if lang == "en":
            pattern = re.compile(rf"\b{re.escape(src)}\b", re.IGNORECASE)
        else:
            pattern = re.compile(rf"(?<![\u0980-\u09FF]){re.escape(src)}(?![\u0980-\u09FF])")
        index.setdefault(words, []).append((src, dst, pattern))
    for entries in index.values():
        entries.sort(key=lambda e: len(e[0]), reverse=True)
    return index


_EN_INDEX = _phrase_index("en")
_BN_INDEX = _phrase_index("bn")


def _translate_sentence(sentence: str, lang: str, index: dict) -> str | None:
    """Translate one sentence; returns ``None`` when coverage is below the
    honesty threshold (the sentence is left untouched by the caller)."""
    tokens = re.findall(r"\w+", sentence, re.UNICODE)
    if not tokens:
        return None
    total = len(tokens)
    covered = 0
    translated = sentence
    matched_phrases: list[str] = []
    for words in sorted(index, reverse=True):
        for src, dst, pattern in index[words]:
            if src in matched_phrases:
                continue
            if pattern.search(translated):
                translated = pattern.sub(dst, translated, count=1)
                covered += len(re.findall(r"\w+", src, re.UNICODE))
                matched_phrases.append(src)
    if covered / total < _MIN_COVERAGE:
        return None
    return translated


def translate_phrase(text: str, target: str) -> TranslationResult:
    """Deterministic phrase-table translation. Pure — no I/O, no settings.

    Sentences whose word coverage is below :data:`_MIN_COVERAGE` stay in the
    original language; quality is ``phrase`` only when at least one sentence
    was actually translated, ``none`` otherwise.
    """
    source = detect_language(text)
    if source == target or not text:
        return TranslationResult(
            translated=text,
            source_lang=source,
            target_lang=target,
            quality="none",
            provider="phrase",
            note="already in the target language",
        )

    digit_map = _BN_TO_ASCII if target == "en" else _ASCII_TO_BN
    index = _BN_INDEX if source == "bn" else _EN_INDEX
    translated_parts: list[str] = []
    translated_any = False
    for part in re.split(r"(?<=[।.!?])\s+|\n+", text):
        if not part.strip():
            translated_parts.append(part)
            continue
        translated = _translate_sentence(part, source, index)
        if translated is None:
            translated_parts.append(part)
        else:
            translated_parts.append(translated.translate(digit_map))
            translated_any = True
    out = "\n".join(translated_parts)
    if not translated_any:
        return TranslationResult(
            translated=text,
            source_lang=source,
            target_lang=target,
            quality="none",
            provider="phrase",
            note="no known phrases matched; text returned unchanged",
        )
    return TranslationResult(
        translated=out,
        source_lang=source,
        target_lang=target,
        quality="phrase",
        provider="phrase",
        note="phrase-table translation (known phrases only)",
    )


def _gateway_translate(text: str, target: str) -> str | None:
    """Ask the configured translation gateway. Strict parsing — any deviation
    (bad JSON, wrong types, network error, timeout) returns ``None`` and the
    caller falls back to the phrase core."""
    url = settings.CHAT_TRANSLATE_GATEWAY_URL
    api_key = settings.CHAT_TRANSLATE_GATEWAY_API_KEY
    if not url:
        return None

    import requests

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = requests.post(
            url,
            json={"text": text, "target_lang": target},
            headers=headers,
            timeout=_GATEWAY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("translation gateway failed (falling back to phrases): %s", exc)
        return None

    translated = data.get("translated")
    if not isinstance(translated, str) or not translated.strip():
        return None
    return translated[:4000]


def translate(text: str, target: str) -> TranslationResult:
    """Provider-aware translate: ``http`` gateway first when configured
    (``CHAT_TRANSLATE_PROVIDER=http``), deterministic phrase core otherwise.
    Never raises; a gateway failure degrades to the phrase core."""
    if target not in ("en", "bn"):
        raise ValueError(f"unsupported target language: {target}")

    provider = (getattr(settings, "CHAT_TRANSLATE_PROVIDER", "") or "phrase").strip().lower()
    if provider == "http":
        gateway_text = _gateway_translate(text, target)
        if gateway_text is not None:
            return TranslationResult(
                translated=gateway_text,
                source_lang=detect_language(text),
                target_lang=target,
                quality="full",
                provider="http",
                note="machine translation from the configured gateway",
            )
    return translate_phrase(text, target)
