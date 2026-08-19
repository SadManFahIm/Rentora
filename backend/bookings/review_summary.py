"""AI Review Summarization (Phase 15 — C5).

Deterministic, statistics-based summary of a room's reviews, produced in
Bengali with a sentiment distribution and the most-discussed topics.

Honesty contract (same as the rest of the platform's AI): this is *statistical
summary*, not human prose. Sentiment comes from the reviewers' own star
ratings (objective); topics come from a bilingual keyword lexicon over the
comments (content-based). The output always carries a ``note`` stating that
it is automatic and shows the review count it was built from, and short
review sets are flagged as statistically unreliable.
"""

from __future__ import annotations

# Minimum reviews before the summary is presented as statistically useful.
_MIN_REVIEWS = 3

# Bilingual topic lexicon. Keys are stable machine ids; labels are the
# Bengali labels shown to users. A comment can mention several topics.
TOPICS: dict[str, dict] = {
    "cleanliness": {
        "label_bn": "পরিচ্ছন্নতা",
        "keywords": ["clean", "tidy", "neat", "dust", "পরিষ্কার", "নোংরা", "পরিচ্ছন্ন"],
    },
    "location": {
        "label_bn": "অবস্থান",
        "keywords": ["location", "area", "near", "close to", "অবস্থান", "এলাকা", "কাছাকাছি"],
    },
    "landlord": {
        "label_bn": "বাড়িওয়ালা",
        "keywords": ["landlord", "owner", "behavior", "helpful", "বাড়িওয়ালা", "মালিক", "আচরণ"],
    },
    "price": {
        "label_bn": "ভাড়া ও দাম",
        "keywords": [
            "price",
            "rent",
            "cost",
            "value",
            "expensive",
            "affordable",
            "ভাড়া",
            "দাম",
            "দামি",
        ],
    },
    "amenities": {
        "label_bn": "সুবিধা",
        "keywords": [
            "furniture",
            "wifi",
            "internet",
            "water",
            "gas",
            "ac",
            "amenities",
            "আসবাব",
            "পানি",
            "গ্যাস",
            "সুবিধা",
            "ইন্টারনেট",
        ],
    },
    "noise": {
        "label_bn": "শব্দ ও নীরবতা",
        "keywords": ["noise", "noisy", "quiet", "peaceful", "শব্দ", "আওয়াজ", "নীরব", "শান্ত"],
    },
    "security": {
        "label_bn": "নিরাপত্তা",
        "keywords": ["safe", "security", "gate", "guard", "নিরাপদ", "সিকিউরিটি", "গেট"],
    },
    "transport": {
        "label_bn": "যাতায়াত",
        "keywords": ["bus", "metro", "commute", "transport", "bus stand", "বাস", "মেট্রো", "যাতায়াত"],
    },
    "light_air": {
        "label_bn": "আলো-বাতাস",
        "keywords": ["light", "sunlight", "ventilat", "air", "আলো", "বাতাস", "রোদ"],
    },
    "overall": {
        "label_bn": "সামগ্রিক অভিজ্ঞতা",
        "keywords": [
            "recommend",
            "nice",
            "good",
            "great",
            "satisfied",
            "ভালো",
            "সন্তুষ্ট",
            "রেকমেন্ড",
            "চমৎকার",
        ],
    },
}

# Bengali digit conversion for the summary text.
_ASCII_TO_BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def _sentiment_of_rating(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "neutral"


def _mentioned_topics(comment: str) -> list[str]:
    """Topic keys a comment touches (bilingual keyword substring match)."""
    lowered = comment.lower()
    return [topic for topic, spec in TOPICS.items() if any(k in lowered for k in spec["keywords"])]


def analyze_reviews(reviews) -> dict:
    """Summarize a queryset/iterable of Review rows.

    Returns the full AI-summary payload: Bengali summary text, sentiment
    distribution (from star ratings), and the most-discussed topics (from
    comments). Deterministic and bounded.
    """
    reviews = list(reviews)
    total = len(reviews)
    avg = round(sum(r.rating for r in reviews) / total, 2) if total else 0.0

    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    topic_counts: dict[str, int] = {}
    for review in reviews:
        sentiment_counts[_sentiment_of_rating(review.rating)] += 1
        for topic in _mentioned_topics(review.comment):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    def pct(count: int) -> int:
        return round(count * 100 / total) if total else 0

    top_topics = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    topics = [
        {"topic": topic, "label_bn": TOPICS[topic]["label_bn"], "count": count}
        for topic, count in top_topics
    ]

    summary_bn = _build_summary_bn(total, avg, sentiment_counts, pct, topics)
    overall = _overall_label(sentiment_counts, total)

    return {
        "summary_bn": summary_bn,
        "sentiment": {
            "positive_pct": pct(sentiment_counts["positive"]),
            "neutral_pct": pct(sentiment_counts["neutral"]),
            "negative_pct": pct(sentiment_counts["negative"]),
            "overall": overall,
        },
        "topics": topics,
        "review_count": total,
        "note": (
            f"Automatic statistical summary from {total} review(s) — built from "
            "ratings and comment keywords, not human-written."
        ),
    }


def _overall_label(sentiment_counts: dict, total: int) -> str:
    if not total:
        return "none"
    positive = sentiment_counts["positive"]
    negative = sentiment_counts["negative"]
    if positive >= negative * 2 and positive >= total * 0.6:
        return "positive"
    if negative >= positive * 2 and negative >= total * 0.4:
        return "negative"
    if negative > positive:
        return "mixed_negative"
    if positive > negative:
        return "mixed_positive"
    return "neutral"


def _bn(n: int) -> str:
    return str(n).translate(_ASCII_TO_BN)


def _build_summary_bn(total, avg, sentiment_counts, pct, topics) -> str:
    if total == 0:
        return "এখনো কোনো রিভিউ নেই।"

    parts: list[str] = []
    parts.append(f"এই লিস্টিংটি {_bn(total)}টি রিভিউ পেয়েছে (গড় {avg:.1f}/৫)।")
    if total < _MIN_REVIEWS:
        parts.append("মাত্র কয়েকটি রিভিউ আছে — পরিসংখ্যানটি এখনো নির্ভরযোগ্য নয়।")
        return " ".join(parts)

    parts.append(
        f"রিভিউকারীদের {_bn(pct(sentiment_counts['positive']))}% ইতিবাচক, "
        f"{_bn(pct(sentiment_counts['negative']))}% নেতিবাচক মত দিয়েছেন।"
    )
    if topics:
        labels = ", ".join(t["label_bn"] for t in topics)
        parts.append(f"সবচেয়ে বেশি আলোচিত বিষয়: {labels}।")
    return " ".join(parts)
