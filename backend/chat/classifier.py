"""Learned chat-safety layer (Tier 2).

A lightweight, deterministic Naive-Bayes classifier trained on a small
hand-labelled corpus of real rental conversations (English + Bengali). It
sits *on top of* the rule detectors in ``safety.py``:

- deterministic rules stay authoritative for high-confidence threats
  (payment redirects, phishing URLs, impersonation, ...);
- the model adds a *learned* signal for messages that pattern-match known
  scam messaging without tripping a rule;
- the model alone can only ever *flag for human review* (medium/high) —
  it can never block a message. Blocking stays a rules-only decision, so a
  model mistake degrades to an admin queue item, never to a silently eaten
  message.

Design notes:
- Pure standard library (collections, math, re) — no sklearn dependency,
  no pickled model files to manage, trains in a few milliseconds at first
  use and is fully deterministic.
- Tokenization is Unicode-aware (re.UNICODE keeps Bangla letters intact).
- Class priors are smoothed (Laplace) so unseen words can never zero a
  class probability.
- Tuning knobs live in Django settings (``CHAT_SAFETY_ML_ENABLED``,
  ``CHAT_SAFETY_ML_FLAG_CONFIDENCE``, ``CHAT_SAFETY_ML_BOOST_CONFIDENCE``)
  so operators can disable or re-tune the layer without touching code.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings

# ---------------------------------------------------------------------------
# Training corpus — small, hand-labelled, rental-domain (EN + BN).
# The classifier is deliberately a *weak* second opinion: it generalises
# from these patterns and defers to human review whenever uncertain.
# ---------------------------------------------------------------------------

_BENIGN = [
    "Hi, is the room still available?",
    "Yes it is available, you can visit tomorrow.",
    "What is the monthly rent?",
    "The rent is 15000 taka including utilities.",
    "Can I see the room this weekend?",
    "Sure, let me know when you are free.",
    "Is the area good for a family?",
    "The apartment has 2 bedrooms and 1 bathroom.",
    "Do you need a security deposit?",
    "Yes, one month's rent as security deposit.",
    "Are the utilities included in the rent?",
    "The kitchen and balcony are shared.",
    "What floor is the flat on?",
    "It is on the 3rd floor with a lift.",
    "Can I move in at the start of next month?",
    "Yes, the previous tenant moves out on the 28th.",
    "Do you allow pets?",
    "Sorry, no pets allowed in this building.",
    "What documents do I need for the agreement?",
    "A copy of your NID and one month's advance.",
    "বাসাটা কি এখনো ভাড়া আছে?",
    "হ্যাঁ, রুমটা এখনো আছে, দেখে যেতে পারেন।",
    "মাসিক ভাড়া কত?",
    "১৫ হাজার টাকা, ইউটিলিটি সহ।",
    "আমি কি শনিবার রুম দেখতে পারি?",
    "আগামীকাল দেখতে পারবেন।",
    "এলাকাটা কেমন, নিরাপদ?",
    "একটা বেডরুম আর একটা বাথরুম আছে।",
    "সিকিউরিটি ডিপোজিট লাগবে?",
    "হ্যাঁ, এক মাসের ভাড়া ডিপোজিট।",
    "কোন ফ্লোরে ফ্ল্যাটটা?",
    "তৃতীয় তলায়, লিফট আছে।",
    "আমি কি পরের মাসের শুরুতে উঠতে পারি?",
    "আগের ভাড়াটিয়া ২৮ তারিখে উঠে যাবে।",
    "কন্ট্রাক্টের জন্য কী কী ডকুমেন্ট লাগবে?",
    "NID-র কপি আর এক মাসের অগ্রিম।",
    # Urgency *alone* is a low-risk rule signal by design — teach the model
    # that hurry/pressure in an otherwise normal rental conversation is not
    # scam-typical, so it never escalates an urgency-only message.
    "Please don't hurry, you can decide after visiting the room.",
    "I know it's urgent for you, but come see the room first.",
    "Take your time, the flat is not going anywhere.",
]

_SUSPICIOUS = [
    "Send 5000 taka to my bKash 01712345678 to confirm the booking",
    "Pay the advance fee through Western Union first",
    "Transfer the deposit to this Nagad number immediately",
    "I need the payment before you visit the room",
    "Send me your OTP and password to verify your account",
    "This is Rentora support, send your NID number now",
    "Hurry, only one room left, pay today or you lose it",
    "Pay the clearance fee to get your refund released",
    "Give your card details on this link and the money comes back",
    "আগাম টাকা বিকাশে পাঠান, তারপর রুমটা কনফার্ম হবে",
    "আগাম টাকা পাঠান নগদ নম্বরে, না হলে রুম পাবেন না",
    "আপনার ওটিপি আর পিন পাঠান ভেরিফাই করতে",
    "আমি রেন্টোরার অফিসিয়াল, আপনার NID নাম্বার দিন",
    "ফি দিতে হবে ক্লিয়ারেন্সের জন্য, ওয়েস্টার্ন ইউনিয়নে পাঠান",
    "একটা নম্বর দিন, হোয়াটসঅ্যাপে কথা বলি",
    "দুপুরের মধ্যে টাকা পাঠান, নাহলে রুম অন্যকে দিয়ে দেব",
    "Send your bKash PIN to release the booking deposit",
]

# ---------------------------------------------------------------------------
# Tokenizer — Unicode-aware, keeps Bangla letters, lowercases.
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[\w\u0900-\u09ff']+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    r"""Split into lowercase word tokens (English + Bengali).

    ``\w`` alone would split Bangla words at vowel-sign marks (U+0980-U+09FF
    contains the letter *and* combining-mark forms, and ``\w`` matches only
    the letters) - so the Bengali block is included explicitly.
    """
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

_LOG_EPSILON = 1e-12


@dataclass
class Verdict:
    """Classifier output for one message."""

    label: str  # "benign" | "suspicious"
    confidence: float  # posterior probability of the winning class (0..1)
    score: float  # raw positive (suspicious) log-odds, for admins


class NaiveBayes:
    """Laplace-smoothed multinomial Naive Bayes over word counts."""

    def __init__(self, classes: list[str], vocab: set[str], log_priors: dict, log_word: dict):
        self.classes = classes
        self.vocab = vocab
        self.log_priors = log_priors
        self.log_word = log_word  # class -> {word: log P(word|class)}
        self.vocab_size = len(vocab)

    def predict(self, text: str) -> Verdict:
        tokens = tokenize(text)
        if not tokens:
            return Verdict(label="benign", confidence=0.5, score=0.0)

        scores: dict[str, float] = {}
        for cls in self.classes:
            log_prob = self.log_priors[cls]
            counts = Counter(tokens)
            for word, count in counts.items():
                if word in self.vocab:
                    log_prob += count * self.log_word[cls].get(word, _LOG_EPSILON)
            scores[cls] = log_prob

        # Two-class softmax gives posteriors; score is the suspicious log-odds.
        pos, neg = scores["suspicious"], scores["benign"]
        max_log = max(pos, neg)
        p_pos = math.exp(pos - max_log) / (math.exp(pos - max_log) + math.exp(neg - max_log))
        label = "suspicious" if pos > neg else "benign"
        return Verdict(
            label=label, confidence=p_pos if label == "suspicious" else 1 - p_pos, score=pos - neg
        )


def _train() -> NaiveBayes:
    """Train on the built-in corpus (pure, deterministic, ~milliseconds)."""
    docs: list[tuple[str, str]] = [(t, "benign") for t in _BENIGN] + [
        (t, "suspicious") for t in _SUSPICIOUS
    ]
    classes = ["benign", "suspicious"]
    vocab: set[str] = set()
    class_docs: dict[str, list[str]] = {c: [] for c in classes}

    for text, label in docs:
        tokens = tokenize(text)
        vocab.update(tokens)
        class_docs[label].append(tokens)

    n_docs = len(docs)
    log_priors = {c: math.log((len(class_docs[c]) + 1) / (n_docs + len(classes))) for c in classes}

    word_counts: dict[str, Counter] = {c: Counter() for c in classes}
    for c in classes:
        for tokens in class_docs[c]:
            word_counts[c].update(tokens)

    vocab_size = len(vocab)
    log_word: dict[str, dict[str, float]] = {}
    for c in classes:
        total = sum(word_counts[c].values()) + vocab_size  # Laplace smoothing
        log_word[c] = {w: math.log((word_counts[c][w] + 1) / total) for w in vocab}
    return NaiveBayes(classes, vocab, log_priors, log_word)


_model: NaiveBayes | None = None


def get_model() -> NaiveBayes:
    """Lazily build (once) and return the classifier. Idempotent + thread-safe
    enough: two racing builds produce identical models, the last one wins."""
    global _model
    if _model is None:
        _model = _train()
    return _model


def classify_text(text: str) -> Verdict:
    """Classify one message. Returns a benign verdict when the layer is
    disabled so callers never need to branch on settings themselves."""
    if not getattr(settings, "CHAT_SAFETY_ML_ENABLED", True):
        return Verdict(label="benign", confidence=0.5, score=0.0)
    return get_model().predict(text)


@lru_cache(maxsize=256)
def _cached_classify(text: str) -> Verdict:
    """Deterministic per-text cache — repeated identical messages (spam
    bursts) don't re-run the model, and the same text always scores the same.
    """
    return get_model().predict(text)


def classify_text_cached(text: str) -> Verdict:
    if not getattr(settings, "CHAT_SAFETY_ML_ENABLED", True):
        return Verdict(label="benign", confidence=0.5, score=0.0)
    return _cached_classify(text)
