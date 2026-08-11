"""Lightweight semantic search over room listings (Phase 11 — Search & Discovery).

Keyword search fails on natural-language queries: "Uttara-তে budget-friendly
student room" shares almost no literal tokens with a listing whose description
says "affordable single room near Gulshan". This module builds a small vector
space model over every room's text (title, area, description, address,
amenities) and ranks rooms by cosine similarity to the query.

Implementation notes
--------------------
- **No heavy ML deps.** We use scikit-learn's ``TfidfVectorizer`` with
  character n-grams (2-5) + ``TruncatedSVD`` (LSA, 50 dims). Character
  n-grams sidestep tokenization entirely, so Bangla (no whitespace
  segmentation needed) and English text share one pipeline — this is what
  makes the search work in both languages for free.
- **Lazy, cached, self-invalidating.** The index is built in-process on
  first use and rebuilt when the newest room's ``updated_at`` moves past the
  fingerprint recorded at build time (a cheap COUNT/MAX query, no signal
  plumbing). Callers never build it themselves.
- **Graceful degradation.** If scikit-learn is unavailable or the build
  fails, ``semantic_rank`` returns ``None`` and the view falls back to the
  keyword path — search still works, just less smart.

The view (``rooms/views.py``) decides when to use this: ``smart=1`` turns on
hybrid ranking (keyword candidates re-ranked semantically, plus semantic
discoveries that keyword search would have missed).
"""

from __future__ import annotations

import logging

from django.db.models import Max

from .models import Room

logger = logging.getLogger(__name__)

# LSA dimensionality — 50 keeps the matrix small while capturing topic
# structure well enough to generalise past exact keyword matches.
_SVD_COMPONENTS = 50
# Character n-gram range. 2-grams catch Bangla syllable pairs, 5-grams catch
# English words like "studio"; narrower than 2 is noise, wider than 5 is
# over-fitting to exact spelling.
_NGRAM_RANGE = (2, 5)


def _room_text(room: Room) -> str:
    """One searchable blob per room — title/area/description/address/amenities."""
    parts = [room.title, room.area, room.description, room.address]
    if room.amenities:
        parts.append(" ".join(room.amenities))
    return " ".join(p for p in parts if p)


class SemanticIndex:
    """TF-IDF + LSA index over all rooms, lazily built and self-invalidating.

    Safe to construct per request: the heavy state (vectorizer + matrix) is
    shared through the module-level ``_INDEX`` singleton and only rebuilt
    when the data changes.
    """

    def __init__(self) -> None:
        self.vectorizer = None
        self.lsa = None
        self.room_ids: list[int] = []
        self.matrix = None
        self._fingerprint: tuple[int, str] | None = None

    def _current_fingerprint(self) -> tuple[int, str]:
        """(row count, newest updated_at) — changes when rooms change."""
        latest = Room.objects.aggregate(max_upd=Max("updated_at"))
        return (Room.objects.count(), str(latest["max_upd"] or ""))

    def is_stale(self) -> bool:
        return self._fingerprint != self._current_fingerprint()

    def build(self) -> bool:
        """(Re)build the index from the current rooms. Returns False on failure."""
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import Normalizer

        rooms = list(
            Room.objects.only("id", "title", "area", "description", "address", "amenities")
        )
        if not rooms:
            self._fingerprint = self._current_fingerprint()
            return False

        texts = [_room_text(r) for r in rooms]
        pipeline = make_pipeline(
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=_NGRAM_RANGE,
                min_df=1,
                sublinear_tf=True,
            ),
            TruncatedSVD(n_components=min(_SVD_COMPONENTS, len(rooms) - 1)),
            Normalizer(copy=False),
        )
        matrix = pipeline.fit_transform(texts)

        self.vectorizer = pipeline.named_steps["tfidfvectorizer"]
        self.lsa = pipeline
        self.room_ids = [r.id for r in rooms]
        self.matrix = matrix
        self._fingerprint = self._current_fingerprint()
        return True

    def search(
        self,
        query: str,
        candidate_ids: list[int] | None = None,
        top_k: int = 60,
    ) -> list[tuple[int, float]]:
        """Rank rooms by cosine similarity to ``query``.

        Returns ``[(room_id, score), ...]`` best-first. When ``candidate_ids``
        is given, scores are computed for that candidate subset only (so the
        NL-filtered pool gets ranked semantically).
        """
        if self.vectorizer is None and not self.build():
            return []
        if not query.strip():
            return []

        q_vec = self.lsa.transform([query])
        # Cosine similarity of the query against every indexed room (rows are
        # L2-normalised, so a single matrix-vector product gives cosines).
        import numpy as np

        scores = np.asarray(q_vec) @ np.asarray(self.matrix).T
        scored: list[tuple[int, float]] = [
            (room_id, float(score)) for room_id, score in zip(self.room_ids, scores[0], strict=True)
        ]
        if candidate_ids is not None:
            wanted = set(candidate_ids)
            scored = [(rid, s) for rid, s in scored if rid in wanted]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


# Module-level singleton so the (expensive) vectorizer/matrix survives across
# requests within a process. Rebuilt lazily via `is_stale()`.
_INDEX: SemanticIndex | None = None


def get_index() -> SemanticIndex:
    global _INDEX
    if _INDEX is None or _INDEX.is_stale():
        index = SemanticIndex()
        try:
            index.build()
        except Exception as exc:
            logger.warning("Semantic index build failed (%s); keyword search only", exc)
            index = None
        _INDEX = index
    return _INDEX


def semantic_rank(
    query: str,
    candidate_ids: list[int] | None = None,
    top_k: int = 60,
) -> list[tuple[int, float]] | None:
    """Best-effort semantic ranking. Returns None when unavailable (fallback)."""
    try:
        index = get_index()
    except Exception:
        return None
    if index is None:
        return None
    try:
        return index.search(query, candidate_ids=candidate_ids, top_k=top_k)
    except Exception as exc:
        logger.warning("Semantic search failed (%s); keyword search only", exc)
        return None


def semantic_candidates(
    query: str,
    candidate_ids: list[int],
    top_k: int = 60,
) -> list[tuple[int, float]] | None:
    """Rank the NL-filtered candidate pool by semantic similarity.

    Returns None if semantic ranking is unavailable (caller falls back to
    default ordering). ``candidate_ids`` is the pool the caller already
    narrowed with natural-language filters (budget/area/type/gender) — we
    never add rooms outside it, so a ৳10,000 budget can't be "discovered"
    past. An empty pool yields an empty result.
    """
    if not candidate_ids:
        return []
    return semantic_rank(query, candidate_ids=candidate_ids, top_k=top_k)
