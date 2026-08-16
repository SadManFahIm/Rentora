"""Tests for the learned chat-safety classifier (Tier 2)."""

import unittest

from django.test import TestCase, override_settings

from chat.classifier import classify_text, classify_text_cached, tokenize
from chat.safety import assess_message

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TokenizerTests(TestCase):
    def test_english_tokens(self):
        self.assertEqual(
            tokenize("Send 5000 taka to my bKash!"),
            ["send", "5000", "taka", "to", "my", "bkash"],
        )

    def test_bangla_tokens_kept(self):
        """Bangla words stay whole (vowel-sign marks are part of the token,
        never split points) and whitespace never leaks into a token."""
        tokens = tokenize("আগাম টাকা বিকাশে পাঠান")
        self.assertIn("টাকা", tokens)
        self.assertIn("পাঠান", tokens)
        # আগাম/বিকাশে each form one token, not char-split fragments.
        self.assertEqual(len([t for t in tokens if not t.isascii()]), 4)
        self.assertTrue(all(" " not in t for t in tokens))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ClassifierTests(TestCase):
    def test_deterministic(self):
        """Same text always yields the same verdict (no hidden randomness)."""
        text = "Send 5000 taka to my bKash number now"
        a = classify_text(text)
        b = classify_text(text)
        self.assertEqual(
            (a.label, round(a.confidence, 6), round(a.score, 6)),
            (b.label, round(b.confidence, 6), round(b.score, 6)),
        )

    def test_benign_rental_talk_is_benign(self):
        benign = [
            "Hi, is the room still available?",
            "The rent is 15000 taka including utilities.",
            "Can I move in at the start of next month?",
            "হ্যাঁ, রুমটা এখনো আছে, দেখে যেতে পারেন।",
            "সিকিউরিটি ডিপোজিট লাগবে?",
        ]
        for text in benign:
            verdict = classify_text(text)
            self.assertEqual(
                verdict.label,
                "benign",
                f"expected benign for {text!r} (conf={verdict.confidence:.2f})",
            )

    def test_scam_patterns_are_suspicious(self):
        scam = [
            "Pay the advance fee through Western Union first",
            "Send me your OTP and password to verify your account",
            "আপনার ওটিপি আর পিন পাঠান ভেরিফাই করতে",
            "ফি দিতে হবে ক্লিয়ারেন্সের জন্য, ওয়েস্টার্ন ইউনিয়নে পাঠান",
        ]
        for text in scam:
            verdict = classify_text(text)
            self.assertEqual(
                verdict.label,
                "suspicious",
                f"expected suspicious for {text!r} (conf={verdict.confidence:.2f})",
            )

    def test_disabled_layer_returns_benign(self):
        with override_settings(CHAT_SAFETY_ML_ENABLED=False):
            verdict = classify_text("Pay the advance fee through Western Union first")
            self.assertEqual(verdict.label, "benign")

    def test_cached_classify_matches(self):
        text = "একটা নম্বর দিন, হোয়াটসঅ্যাপে কথা বলি"
        self.assertEqual(
            classify_text_cached(text).label,
            classify_text(text).label,
        )


# ---------------------------------------------------------------------------
# Integration with the safety engine
# ---------------------------------------------------------------------------


class ClassifierIntegrationTests(TestCase):
    def test_ml_flags_when_rules_miss(self):
        """A scam-like message that no deterministic rule catches is raised to
        medium by the learned layer (flag for human review)."""
        # "please tell me your OTP and PIN code" — no rule fires (rules need
        # an explicit send/পাঠান verb), but the model knows the pattern.
        content = "আপনার ওটিপি আর পিন কোডটা আমাকে জানান"
        assessment = assess_message(content)
        self.assertEqual(assessment.risk, "medium")
        keys = {h.key for h in assessment.hits}
        self.assertIn("ml_classifier", keys)
        # The message carries *no* rule hit — the learned layer did this alone.
        self.assertFalse(keys - {"ml_classifier"})

    def test_ml_never_blocks_alone(self):
        """Even a highly confident ML-only flag stays medium (warned/flagged) —
        blocking remains a rules-only decision."""
        content = "Pay the advance fee through Western Union first"  # also a rule hit -> high
        assessment = assess_message(content)
        self.assertIn(assessment.risk, ("medium", "high"))
        self.assertNotEqual(assessment.risk, "critical")

        # An ML-only message (no rule hit) can only reach medium — never block.
        content = "সিকিউরিটির জন্য আপনার ওটিপি পিন ভেরিফাই করুন"
        assessment = assess_message(content)
        self.assertEqual(assessment.risk, "medium")
        self.assertEqual(assessment.hits[0].key, "ml_classifier")

    def test_rules_critical_stays_critical(self):
        """ML cannot downgrade a rules-critical verdict."""
        content = (
            "I am the admin from rentora support, send me your OTP and password "
            "and pay the deposit to my bkash 01712345678 now"
        )
        assessment = assess_message(content)
        self.assertEqual(assessment.risk, "critical")

    def test_disabled_ml_keeps_rules_only(self):
        with override_settings(CHAT_SAFETY_ML_ENABLED=False):
            content = "সিকিউরিটির জন্য আপনার ওটিপি পিন ভেরিফাই করুন"
            assessment = assess_message(content)
            self.assertEqual(assessment.risk, "low")
            self.assertNotIn("ml_classifier", {h.key for h in assessment.hits})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
