"""Neural semantic embeddings for room search, with a zero-dependency fallback.

The project deliberately avoids heavy ML dependencies, so the embedding
provider is pluggable and degrades gracefully:

1. **SentenceTransformerProvider** — real multilingual neural embeddings
   (``sentence-transformers`` + ``SEMANTIC_EMBEDDING_MODEL``). Only active
   when the optional package is installed; the model is a lazy singleton.
2. **LiteEmbeddingProvider** — always-available synonym-expanded char-ngram
   hashing (stdlib + numpy). It bakes a small curated bilingual concept
   dictionary ("affordable" ↔ "কম দাম", "student" ↔ "শিক্ষার্থী") into
   fixed-size vectors, so **Bangla/English/Banglish queries find synonyms
   across scripts with zero model downloads** — enough to make hybrid search
   meaningfully semantic in dev/CI, and a clean baseline to upgrade by
   installing sentence-transformers.

Room embeddings are computed **once per index fingerprint** (same
self-invalidating pattern as ``rooms/semantic.py``) and cached in-process —
never per search request. The query is embedded fresh (one vector), then
scored against the cached matrix.

If *anything* fails (no numpy, model download broken, …), ``semantic_scores``
returns None and the caller falls back to the TF-IDF/LSA index — search still
works, just less smart.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import unicodedata

import numpy as np
from django.conf import settings
from django.db.models import Max

from .models import Room

logger = logging.getLogger(__name__)

# Fixed dimension of the lite (hash-based) provider. Big enough to separate
# concepts, small enough to keep the cached room matrix cheap.
_LITE_DIM = 256
# Character n-gram range for the lite provider — mirrors semantic.py's choice:
# 2-grams catch Bangla syllable pairs, 5-grams catch English words.
_LITE_NGRAM_RANGE = (2, 5)

# Bilingual concept dictionary: concept -> expansion terms (the concept's
# own surface forms across English/Bangla/Banglish). A room text matching ANY
# expansion term contributes ALL of them as tokens, so "affordable room" and
# "কম বাজেটের রুম" land near each other in vector space.
CONCEPT_TERMS: dict[str, tuple[str, ...]] = {
    "affordable": (
        "affordable",
        "cheap",
        "budget",
        "economical",
        "কম দাম",
        "সস্তা",
        "কম বাজেট",
        "বাজেট",
    ),
    "student": ("student", "students", "শিক্ষার্থী", "ছাত্র", "ছাত্রী", "student-friendly", "campus"),
    "furnished": ("furnished", "furniture", "সজ্জিত", "আসবাবপত্র"),
    "balcony": ("balcony", "বারান্দা"),
    "metro": ("metro", "mrt", "মেট্রো", "স্টেশন", "station"),
    "university": ("university", "college", "বিশ্ববিদ্যালয়", "কলেজ"),
    "family": ("family", "পরিবার", "ফ্যামিলি"),
    "shared": ("shared", "share", "শেয়ার", "ভাগ করা"),
    "single": ("single", "private", "একক"),
    "studio": ("studio", "স্টুডিও"),
    "ac": ("ac", "air conditioner", "এসি", "শীতাতপ"),
    "wifi": ("wifi", "internet", "ওয়াইফাই", "ইন্টারনেট"),
    "quiet": ("quiet", "peaceful", "calm", "শান্ত", "নীরব"),
    "secure": ("secure", "safe", "নিরাপদ", "সেফ"),
    "modern": ("modern", "contemporary", "আধুনিক"),
    "spacious": ("spacious", "big", "large", "প্রশস্ত", "বড়"),
    "market": ("bazar", "market", "shopping", "বাজার", "শপিং"),
    "parking": ("parking", "garage", "পার্কিং", "গ্যারেজ"),
    "garden": ("garden", "বাগান"),
    "kitchen": ("kitchen", "রান্নাঘর", "রান্না"),
    "bathroom": ("bathroom", "attached bath", "বাথরুম", "টয়লেট"),
    "nearby": ("near", "close to", "walking distance", "কাছে", "নিকটে", "পাশে"),
    "view": ("view", "city view", "ভিউ", "দৃশ্য"),
    "new": ("new", "fresh", "নতুন"),
    "clean": ("clean", "tidy", "পরিষ্কার"),
    "night": ("night", "রাতে", "রাত"),
    "office": ("office", "অফিস"),
    "executive": ("executive", "professionals", "এক্সিকিউটিভ"),
}

_CONCEPT_LIST: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    sorted(CONCEPT_TERMS.items(), key=lambda kv: -len(kv[1][0]))
)


class EmbeddingProvider:
    """Minimal interface: ``encode(texts)`` -> L2-normalized row vectors."""

    name: str = "base"

    def encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


def _normalize_lite(text: str) -> str:
    return unicodedata.normalize("NFC", (text or "").lower())


class SentenceTransformerProvider(EmbeddingProvider):
    """Real multilingual neural embeddings (optional heavy dependency)."""

    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        self._model = None
        self.model_name = model_name

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)


class LiteEmbeddingProvider(EmbeddingProvider):
    """Zero-dependency synonym-expanded char-ngram hashing.

    Each text becomes a 256-dim bag of hashed char n-grams; words that match
    a concept in ``CONCEPT_TERMS`` additionally inject that concept's whole
    expansion set, which is what carries meaning across Bangla/English.
    """

    name = "lite-synonym-hash"

    def __init__(self, dim: int = _LITE_DIM) -> None:
        self.dim = dim

    def _text_tokens(self, text: str) -> list[str]:
        normalized = _normalize_lite(text)
        tokens: list[str] = []
        for size in range(_LITE_NGRAM_RANGE[0], _LITE_NGRAM_RANGE[1] + 1):
            tokens.extend(
                normalized[i : i + size] for i in range(max(len(normalized) - size + 1, 0))
            )
        # Concept expansion: any matched concept injects its whole term set.
        for _concept, terms in _CONCEPT_LIST:
            for term in terms:
                if term in normalized:
                    tokens.extend(terms)
                    break
        return tokens

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts = np.zeros(self.dim, dtype=np.float32)
            for token in self._text_tokens(text):
                counts[_hash_token(token, self.dim)] += 1.0
            if counts.sum() > 0:
                counts = np.log1p(counts)
                norm = float(np.linalg.norm(counts))
                if norm > 0:
                    counts /= norm
            matrix[row] = counts
        return matrix


def _hash_token(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


def _room_text(room: Room) -> str:
    """One searchable blob per room — same fields the TF-IDF index uses."""
    parts = [room.title, room.area, room.description, room.address]
    if room.amenities:
        parts.append(" ".join(str(a) for a in room.amenities))
    return " ".join(p for p in parts if p)


def get_provider() -> EmbeddingProvider | None:
    """Pick the best available provider, or None when embeddings are disabled.

    Order: sentence-transformers (when the package is installed) -> the
    zero-dependency lite provider. The optional import is checked eagerly so
    a missing package never even constructs the heavy provider; a model that
    installs but fails to load is caught downstream by ``semantic_scores``
    and degrades to the TF-IDF leg.
    """
    if not getattr(settings, "SEMANTIC_SEARCH_ENABLED", True):
        return None
    if importlib.util.find_spec("sentence_transformers") is not None:
        try:
            return SentenceTransformerProvider(
                getattr(
                    settings,
                    "SEMANTIC_EMBEDDING_MODEL",
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                )
            )
        except Exception as exc:  # broken install
            logger.debug("sentence-transformers unusable (%s); using lite provider", exc)
    return LiteEmbeddingProvider()


class EmbeddingIndex:
    """Cached embedding matrix over all rooms, self-invalidating by fingerprint.

    Building the lite matrix is cheap enough to rebuild on demand; the
    sentence-transformer matrix is expensive, so it is computed once and
    reused until room data changes (same pattern as ``SemanticIndex``).
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider
        self.room_ids: list[int] = []
        self.matrix: np.ndarray | None = None
        self._fingerprint: tuple[int, str] | None = None

    def _current_fingerprint(self) -> tuple[int, str]:
        latest = Room.objects.aggregate(max_upd=Max("updated_at"))
        return (Room.objects.count(), str(latest["max_upd"] or ""))

    def is_stale(self) -> bool:
        return self._fingerprint != self._current_fingerprint()

    def build(self) -> bool:
        rooms = list(
            Room.objects.only("id", "title", "area", "description", "address", "amenities")
        )
        if not rooms:
            self._fingerprint = self._current_fingerprint()
            return False
        texts = [_room_text(r) for r in rooms]
        self.room_ids = [r.id for r in rooms]
        self.matrix = self.provider.encode(texts)
        self._fingerprint = self._current_fingerprint()
        return True


_INDEX: EmbeddingIndex | None = None


def get_index() -> EmbeddingIndex | None:
    """Module-level cached index (safe to construct per request)."""
    global _INDEX
    try:
        provider = get_provider()
        if provider is None:
            return None
        if _INDEX is None or _INDEX.is_stale():
            index = EmbeddingIndex(provider)
            if not index.build():
                return None
            _INDEX = index
        return _INDEX
    except Exception as exc:
        logger.warning("Embedding index unavailable (%s); TF-IDF/keyword fallback", exc)
        return None


def semantic_scores(
    query: str,
    candidate_ids: list[int] | None = None,
    top_k: int | None = None,
) -> list[tuple[int, float]] | None:
    """Cosine similarity of ``query`` against room embeddings, best-first.

    Returns None when embeddings are unavailable/disabled (caller falls back
    to TF-IDF or keyword ranking). ``candidate_ids`` restricts scoring to the
    hard-filtered pool.
    """
    try:
        index = get_index()
        if index is None or index.matrix is None or not query.strip():
            return None
        query_vec = index.provider.encode([query])[0]
        scores = np.asarray(index.matrix) @ query_vec
        scored: list[tuple[int, float]] = [
            (room_id, float(score)) for room_id, score in zip(index.room_ids, scores, strict=True)
        ]
        if candidate_ids is not None:
            wanted = set(candidate_ids)
            scored = [(rid, s) for rid, s in scored if rid in wanted]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        if top_k is not None:
            scored = scored[:top_k]
        return scored
    except Exception as exc:
        logger.warning("Embedding scoring failed (%s); TF-IDF/keyword fallback", exc)
        return None
