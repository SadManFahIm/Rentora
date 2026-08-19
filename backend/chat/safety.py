"""Chat Safety Engine (Phase 12.3).

Rule-based fraud/safety detection applied to every chat message, on both the
REST and WebSocket creation paths. Detection is deliberately *conservative*:
it warns (medium), flags (high) or blocks (critical) — it never silently
deletes anything, and it never claims certainty. The engine mirrors the fraud
app's detector style (key + risk + message + machine detail), reuses the
append-only audit/notification infra where relevant, and records what it found
as *metadata only* — detector keys and short matched fragments — never full
conversation content.

Policy is configurable via Django settings (``CHAT_SAFETY_ENABLED``,
``CHAT_SAFETY_BLOCK_LEVEL``, ``CHAT_SAFETY_FLAG_LEVEL``) so operators can tune
how aggressive the engine is without touching code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Risk ordering — a message's overall risk is the *highest* detector hit.
RISK_ORDER = ["low", "medium", "high", "critical"]

# The notice shown in place of a blocked message. Deliberately vague about the
# exact reason (we don't want to teach scammers which phrase tripped the net).
BLOCKED_CONTENT = "🚫 Message blocked for safety review."

# Recipient-facing warnings, matching the spec's example copy exactly.
WARNINGS = {
    "medium": "Be careful sharing payment information.",
    "high": "Potentially unsafe payment request detected.",
}

# How far back (and how often) a repeated-suspicious check looks: the same
# sender hitting the same detector twice in this window escalates by one risk
# level (urgency pressure + repetition is how scams grind people down).
REPEAT_WINDOW_MINUTES = 30
REPEAT_MIN_HITS = 2

# Learned-classifier layer (Tier 2). The model adds a *learned* signal for
# messages that pattern-match known scam messaging without tripping a rule.
# It can only ever raise a message to medium (flag for human review) or
# boost a rule-based medium to high — it can never block, and it never
# overrides a rules verdict. Thresholds are posteriors (0..1).
ML_FLAG_CONFIDENCE = 0.60
ML_BOOST_CONFIDENCE = 0.85
ML_HIT_KEY = "ml_classifier"
ML_HIT_LABEL = "Pattern matches known scam messaging"


@dataclass
class DetectorHit:
    """One detector's match: which rule fired, at what risk, and the matched
    fragment(s). Fragments are short, sanitized snippets for admins — never
    the whole message."""

    key: str
    label: str
    risk: str
    fragments: list[str] = field(default_factory=list)


@dataclass
class Assessment:
    """The engine's verdict on one message."""

    risk: str = "low"
    hits: list[DetectorHit] = field(default_factory=list)
    repeated: bool = False

    @property
    def risk_index(self) -> int:
        return RISK_ORDER.index(self.risk)


# A Bangladeshi mobile number — the classic "send the deposit to this bKash
# number" vector. Bangladesh numbers: 01[3-9]xxxxxxxx.
_BD_NUMBER = r"(?:\+?880|0)?1[3-9]\d{8}"

# Detector table. Each entry: key, label, base risk, and compiled patterns.
# Patterns are written to be *precise* (avoid flagging ordinary mentions of
# bKash / deposits, which are legitimate parts of the rental flow) — a wallet
# name alone is not suspicious; a wallet + a number / payment verb is.
DETECTORS: list[dict] = [
    {
        "key": "payment_redirect",
        "label": "Off-platform payment request",
        "risk": "high",
        "patterns": [
            # "send/pay/deposit … [to] bkash/nagad/…" (+number)
            re.compile(
                r"\b(send|pay|transfer|deposit|advance|pathao|add)\b.{0,40}"
                r"\b(bkash|nagad|rocket|upay|বিকাশ|নগদ|রকেট)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(bkash|nagad|rocket|upay|বিকাশ|নগদ|রকেট)\b.{0,40}\b(number|no\.?|namer|নাম্বার|নম্বর)\b",
                re.IGNORECASE,
            ),
            # wallet name near a Bangladeshi mobile number
            re.compile(
                rf"\b(bkash|nagad|rocket|upay|বিকাশ|নগদ|রকেট)\b[^\n]{{0,30}}{_BD_NUMBER}",
                re.IGNORECASE,
            ),
            # "টাকা পাঠান / দিন / দেন" (send money) + wallet
            re.compile(r"\b(টাকা পাঠান|টাকা দিন|টাকা দেন|পাঠিয়ে দেন)\b"),
        ],
    },
    {
        "key": "advance_payment",
        "label": "Advance payment before viewing",
        "risk": "high",
        "patterns": [
            re.compile(
                r"\b(advance|booking money|booking fee|আগাম|বুকিং)\b.{0,30}"
                r"\b(pay|send|give|পাঠান|দিন|দেন|দিবেন)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(pay|send)\b.{0,20}\b(before|first|now|today)\b",
                re.IGNORECASE,
            ),
        ],
    },
    {
        "key": "phishing_url",
        "label": "Suspicious link",
        "risk": "medium",
        "patterns": [
            # URL shorteners — a favourite phishing vector
            re.compile(
                r"\b(bit\.ly|tinyurl\.com|t\.ly|cutt\.ly|is\.gd|rb\.gy|shorturl\.at)\b",
                re.IGNORECASE,
            ),
            # raw-IP links
            re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}\b"),
            # lookalike domains of trusted brands (rent0ra, sslcommerz-…)
            re.compile(
                r"https?://[^\s]*\b(rent0ra|rentora[^s]|sslcommerz|bkash|nagad)[^.\s]*\.(com|net|org|xyz|top|info)\b",
                re.IGNORECASE,
            ),
        ],
    },
    {
        "key": "contact_redirect",
        "label": "Off-platform contact request",
        "risk": "medium",
        "patterns": [
            re.compile(r"\b(whatsapp|telegram|viber|imo|wechat|signal)\b", re.IGNORECASE),
            re.compile(r"\b(call|contact|message|email|mail)\s+me\s+(at|on|in)\b", re.IGNORECASE),
            # "this is my personal number …" with a number
            re.compile(rf"\b(my|personal)\b[^\n]{{0,20}}{_BD_NUMBER}", re.IGNORECASE),
        ],
    },
    {
        "key": "urgency",
        "label": "Urgency pressure",
        "risk": "low",
        "patterns": [
            re.compile(
                r"\b(hurry|urgent|now or never|today only|last chance|act now|"
                r"only \d+ (rooms?|seats?|left)|first come first)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\b(এখনই|আজই|ঝটপট|শেষ সুযোগ|দ্রুত|জলদি|জলদী)\b"),
        ],
    },
    {
        "key": "scam_phrase",
        "label": "Common scam phrase",
        "risk": "medium",
        "patterns": [
            re.compile(
                r"\b(western union|moneygram|transfer fee|advance fee|processing fee|"
                r"clearance fee|refundable deposit fee)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\b(আগাম টাকা|এডভান্স ফি|ফি দিতে হবে)\b"),
        ],
    },
    {
        "key": "impersonation",
        "label": "Impersonation of Rentora / staff",
        "risk": "high",
        "patterns": [
            re.compile(
                r"\b(i am|this is)\s+(the\s+)?(admin|moderator|support|official|staff)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(from|of|at)\s+rentora\s+(support|team|official|staff|admin)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\brentora\s+(official|officially)\b", re.IGNORECASE),
            re.compile(r"\b(আমি রেন্টোরা|রেন্টোরার অফিসিয়াল|রেন্টোরা টিম)\b"),
        ],
    },
    {
        "key": "credential_request",
        "label": "Request for sensitive credentials",
        "risk": "high",
        "patterns": [
            re.compile(
                r"\b(send|give|share|tell)\s+(me\s+)?(your\s+)?(otp|pin|password|passcode|nid|verification code)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(otp|password|pin|nid|ওটিপি|পাসওয়ার্ড)\b.{0,30}\b(send|দাও|দিন|পাঠান)\b",
                re.IGNORECASE,
            ),
        ],
    },
    # Phase 15, D9 — deep impersonation: a staff claim *plus* a claim of
    # authority to act on the account/booking (approve, cancel, refund,
    # release, verify…). Bare "I am admin" is already caught by the
    # `impersonation` detector; this one targets the escalation: "I am the
    # admin and I can approve your booking".
    {
        "key": "staff_impersonation_deep",
        "label": "Deep staff impersonation (authority claim)",
        "risk": "high",
        "patterns": [
            re.compile(
                r"\b(admin|moderator|support|official|staff)\b[^\n]{0,40}"
                r"\b(approve|approval|cancel|refund|release|verify|activate|unlock|access|authorize|suspend)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(i am|this is|im|i'm)\s+(the\s+)?(site|platform|website)\s+(admin|moderator|owner)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"(অ্যাডমিন|সাপোর্ট|অফিসিয়াল|স্টাফ)[^\n]{0,40}"
                r"(অ্যাপ্রুভ|ক্যানসেল|রিফান্ড|রিলিজ|ভেরিফাই|অ্যাক্সেস|অ্যাকাউন্ট|বুকিং|সাসপেন্ড)",
            ),
            re.compile(r"(সাইটের|প্ল্যাটফর্মের)\s*(অ্যাডমিন|মডারেটর|মালিক)"),
        ],
    },
    # Phase 15, D9 — advance-fee-for-outcome scams: pay a fee to unlock a
    # refund / release / clearance / verification. The classic "pay to get
    # your money back" trap.
    {
        "key": "scam_advance",
        "label": "Advance-fee / fee-for-refund scam",
        "risk": "high",
        "patterns": [
            re.compile(
                r"\b(pay|send|deposit|transfer|remit)\b[^\n]{0,30}\b(fee|charges?|amount)\b"
                r"[^\n]{0,30}\b(release|refund|clearance|processing|activation|verification|withdrawal)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(release|refund|clearance|processing|activation|verification)\b"
                r"[^\n]{0,30}\b(fee|charg?|payment|টাকা|ফি)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"(ফি|টাকা জমা|টাকা পাঠান)[^\n]{0,30}(রিফান্ড|রিলিজ|ক্লিয়ারেন্স|প্রসেসিং|অ্যাক্টিভেশন)",
            ),
            re.compile(r"(রিফান্ড|রিলিজ|ক্লিয়ারেন্স)[^\n]{0,30}(ফি|টাকা)"),
        ],
    },
    # Phase 15, D9 — pressure to move off-platform *with a consequence*:
    # "talk on WhatsApp or the room is gone". Combines the off-platform vector
    # with the urgency lever scammers use to close fast.
    {
        "key": "external_contact_pressure",
        "label": "Off-platform contact under pressure",
        "risk": "medium",
        "patterns": [
            re.compile(
                r"\b(whatsapp|telegram|viber|imo|wechat)\b[^\n]{0,40}\b(or|otherwise|else)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(talk|chat|message|contact|msg)\b[^\n]{0,30}\b(whatsapp|telegram|viber|imo|wechat)\b"
                r"[^\n]{0,40}\b(or|otherwise|else)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"(কথা বলি|কথা বলুন|যোগাযোগ|মেসেজ|চ্যাট)[^\n]{0,30}"
                r"(হোয়াটসঅ্যাপে?|টেলিগ্রামে?|ভাইবারে?|ইমোতে?)"
                r"[^\n]{0,30}(না হলে|নাহলে|নইলে|অথবা)",
            ),
            re.compile(
                r"(হোয়াটসঅ্যাপে?|টেলিগ্রামে?|ভাইবারে?|ইমোতে?)[^\n]{0,30}"
                r"(কথা বলি|কথা বলুন|যোগাযোগ|মেসেজ|চ্যাট)"
                r"[^\n]{0,30}(না হলে|নাহলে|নইলে|অথবা)",
            ),
        ],
    },
]


def _fragment(match: re.Match) -> str:
    """Short, single-line snippet of a match for admin metadata — never the
    whole message."""
    text = " ".join(match.group(0).split())
    return text[:80]


def detect(content: str) -> list[DetectorHit]:
    """Run every detector over the message. Pure function — no DB, no I/O."""
    hits: list[DetectorHit] = []
    for detector in DETECTORS:
        matched_fragments: list[str] = []
        for pattern in detector["patterns"]:
            for match in pattern.finditer(content):
                matched_fragments.append(_fragment(match))
                if len(matched_fragments) >= 3:  # keep metadata bounded
                    break
        if matched_fragments:
            hits.append(
                DetectorHit(
                    key=detector["key"],
                    label=detector["label"],
                    risk=detector["risk"],
                    fragments=matched_fragments,
                )
            )
    return hits


def _max_risk(hits: list[DetectorHit]) -> str:
    if not hits:
        return "low"
    return max(hits, key=lambda h: RISK_ORDER.index(h.risk)).risk


def detect_crosslingual(content: str) -> list[DetectorHit]:
    """Run the detectors over the original text and — when the text is Bangla
    and the phrase-table core can normalize it to English — over the
    normalized version too (Phase 15, B1).

    Hits are merged by detector key: the higher risk wins and fragments are
    unioned, so an English-only pattern (e.g. ``western union``) can catch a
    Bengali payload that the Bengali patterns alone would miss. This is the
    chat-translation module's contribution to the safety engine: translation
    is used to *re-read* the message, never to change what the sender wrote.
    Pure function — no I/O, no DB, no network (the phrase core is
    deterministic and the gateway is deliberately never consulted here).
    """
    hits = {h.key: h for h in detect(content)}

    from .translation import detect_language, translate_phrase

    if detect_language(content) != "bn":
        return list(hits.values())

    normalized = translate_phrase(content, "en")
    if normalized.quality != "phrase":
        return list(hits.values())

    for h in detect(normalized.translated):
        existing = hits.get(h.key)
        if existing is None or RISK_ORDER.index(h.risk) > RISK_ORDER.index(existing.risk):
            hits[h.key] = h
    return list(hits.values())


def _contextual_escalation(hits: list[DetectorHit], chat_room, sender) -> bool:
    """Phase 15, D9 — an authority claim only makes sense from someone with
    authority. If a sender claims to be staff/admin in a real conversation
    but is not actually staff (or a room admin), the claim is an active
    attack: escalate the risk by one level.

    ``chat_room``/``sender`` are optional — without them there is no context
    to judge against, so the check is skipped (pure detection stays hermetic).
    """
    if chat_room is None or sender is None:
        return False
    authority_keys = {"impersonation", "staff_impersonation_deep"}
    if not ({h.key for h in hits} & authority_keys):
        return False
    # A genuine staff/admin sender claiming authority is legitimate — only
    # non-authorised senders get escalated.
    return not (sender.is_staff or getattr(sender, "role", "") == "admin")


def assess_message(content: str, chat_room=None, sender=None) -> Assessment:
    """Assess one message: run the detectors (including the cross-lingual
    scan), then escalate for *repeated* suspicious behaviour by the same
    sender in the same room.

    ``chat_room``/``sender`` are optional — without them the repetition check
    is skipped (pure detection), which keeps the unit tests hermetic.
    """
    hits = detect_crosslingual(content)
    risk = _max_risk(hits)

    # Multiple *distinct* high-risk signals together (e.g. impersonation +
    # credential request + payment redirect) are critical-grade: a single
    # high is a warning to review, a stack of them is an active attack.
    if len({h.key for h in hits if h.risk == "high"}) >= 2:
        risk = "critical"

    # Phase 15, D9 — deep impersonation in a real conversation by a
    # non-authorised sender is treated as an active attack.
    if _contextual_escalation(hits, chat_room, sender):
        risk = RISK_ORDER[min(RISK_ORDER.index(risk) + 1, len(RISK_ORDER) - 1)]

    # Learned layer (Tier 2): a deterministic Naive-Bayes model trained on
    # real rental-conversation patterns sits on top of the rules. If it is
    # confident the message is scam-like but no rule fired, raise to medium
    # (which flags it for human review — never blocks). If it is *very*
    # confident and a rule already found medium, boost one level. It can
    # never produce critical on its own and never downgrades a rule verdict.
    from .classifier import classify_text_cached

    verdict = classify_text_cached(content)
    if verdict.label == "suspicious" and verdict.confidence > 0:
        flag_conf = getattr(settings, "CHAT_SAFETY_ML_FLAG_CONFIDENCE", ML_FLAG_CONFIDENCE)
        boost_conf = getattr(settings, "CHAT_SAFETY_ML_BOOST_CONFIDENCE", ML_BOOST_CONFIDENCE)
        if risk == "low" and verdict.confidence >= flag_conf:
            hits.append(
                DetectorHit(
                    key=ML_HIT_KEY,
                    label=ML_HIT_LABEL,
                    risk="medium",
                    fragments=["learned-pattern match"],
                )
            )
            risk = "medium"
        elif risk == "medium" and verdict.confidence >= boost_conf:
            hits.append(
                DetectorHit(
                    key=ML_HIT_KEY,
                    label=ML_HIT_LABEL,
                    risk="high",
                    fragments=["learned-pattern match (high confidence)"],
                )
            )
            risk = "high"

    repeated = False
    if hits and chat_room is not None and sender is not None:
        from .models import ChatSafetyEvent

        recent = ChatSafetyEvent.objects.filter(
            sender=sender,
            chat_room=chat_room,
            created_at__gte=timezone.now() - timedelta(minutes=REPEAT_WINDOW_MINUTES),
        )
        keys = {h.key for h in hits}
        # Count prior events sharing any of this message's detector keys.
        repeats = 0
        for event in recent.only("detectors"):
            event_keys = {d.get("key") for d in (event.detectors or [])}
            if event_keys & keys:
                repeats += 1
        if repeats >= REPEAT_MIN_HITS:
            repeated = True
            # Escalate one level (low→medium, medium→high, high→critical).
            risk = RISK_ORDER[min(RISK_ORDER.index(risk) + 1, len(RISK_ORDER) - 1)]

    return Assessment(risk=risk, hits=hits, repeated=repeated)


def apply_policy(assessment: Assessment) -> str:
    """Map an assessment to an outcome using the configured policy.

    Returns one of ``warned`` | ``flagged`` | ``blocked`` (``low`` risk with
    no hits yields ``warned``-nothing — callers treat it as allowed).
    """
    block_level = getattr(settings, "CHAT_SAFETY_BLOCK_LEVEL", "critical")
    flag_level = getattr(settings, "CHAT_SAFETY_FLAG_LEVEL", "high")

    def idx(level: str) -> int:
        return RISK_ORDER.index(level if level in RISK_ORDER else "critical")

    if assessment.risk_index >= idx(block_level):
        return "blocked"
    if assessment.risk_index >= idx(flag_level):
        return "flagged"
    if assessment.risk_index > 0:
        return "warned"
    return "allowed"


def safety_payload(assessment: Assessment, outcome: str) -> dict:
    """The slice of the assessment the client sees (safe, never raw content)."""
    payload: dict = {
        "risk_level": assessment.risk,
        "outcome": outcome,
        "blocked": outcome == "blocked",
    }
    if outcome == "warned" or outcome == "flagged":
        payload["warning"] = WARNINGS.get(assessment.risk, "Please be cautious.")
    if assessment.hits:
        payload["detectors"] = [{"key": h.key, "label": h.label} for h in assessment.hits]
    return payload


def record_safety_event(chat_room, sender, message, assessment: Assessment, outcome: str):
    """Persist a ChatSafetyEvent for any non-allowed outcome. Metadata only —
    detector keys + short fragments — never the full message content."""
    if outcome == "allowed" or not assessment.hits:
        return None
    from .models import ChatSafetyEvent

    return ChatSafetyEvent.objects.create(
        chat_room=chat_room,
        sender=sender,
        message=message,
        risk_level=assessment.risk,
        outcome=outcome,
        detectors=[
            {"key": h.key, "label": h.label, "fragments": h.fragments} for h in assessment.hits
        ],
        detail={"repeated": assessment.repeated, "hit_count": len(assessment.hits)},
    )


def run_chat_safety(content: str, chat_room, sender) -> tuple[str, Assessment, str]:
    """Full pipeline for one outgoing message (REST and WebSocket both call
    this): assess → apply policy → decide the content that will actually be
    stored.

    Returns ``(final_content, assessment, outcome)``. When blocked, the
    returned content is the safety notice and the sender's raw text is
    discarded (never stored, never broadcast).
    """
    if not getattr(settings, "CHAT_SAFETY_ENABLED", True):
        return content, Assessment(), "allowed"

    assessment = assess_message(content, chat_room=chat_room, sender=sender)
    outcome = apply_policy(assessment)
    if outcome == "blocked":
        logger.warning(
            "chat_safety blocked message: room=%s sender=%s risk=%s detectors=%s",
            chat_room.pk if chat_room else None,
            sender.pk if sender else None,
            assessment.risk,
            [h.key for h in assessment.hits],
        )
        return BLOCKED_CONTENT, assessment, outcome
    return content, assessment, outcome
