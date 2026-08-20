"""Phase 15 (B1) — Chat live translation EN⇄BN tests.

Covers the deterministic phrase-table core, language detection, digit
conversion, the optional http gateway (with graceful fallback), the REST
endpoint, and the safety-engine integration: a Bengali payload that the
Bengali patterns alone miss must be caught via the cross-lingual scan.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .safety import assess_message, detect
from .translation import detect_language, translate, translate_phrase

User = get_user_model()


class LanguageDetectionTests(APITestCase):
    def test_english_text(self):
        self.assertEqual(detect_language("What is the monthly rent?"), "en")

    def test_bangla_text(self):
        self.assertEqual(detect_language("মাসিক ভাড়া কত?"), "bn")

    def test_mixed_text_is_bangla_when_dominant(self):
        self.assertEqual(detect_language("ভাড়া কত bro?"), "bn")

    def test_empty_text_is_english(self):
        self.assertEqual(detect_language(""), "en")

    def test_digits_only_is_english(self):
        self.assertEqual(detect_language("01712345678"), "en")


class PhraseTranslationTests(APITestCase):
    def test_en_to_bn_known_phrase(self):
        result = translate_phrase("What is the monthly rent?", "bn")
        self.assertEqual(result.quality, "phrase")
        self.assertEqual(result.source_lang, "en")
        self.assertIn("মাসিক ভাড়া", result.translated)

    def test_bn_to_en_known_phrase(self):
        result = translate_phrase("মাসিক ভাড়া কত?", "en")
        self.assertEqual(result.quality, "phrase")
        self.assertIn("monthly rent", result.translated)

    def test_bangla_digits_converted_to_ascii(self):
        result = translate_phrase("আমাকে পাঠান ০১৭১২৩৪৫৬৭৮", "en")
        self.assertEqual(result.quality, "phrase")
        self.assertIn("01712345678", result.translated)

    def test_ascii_digits_converted_to_bangla(self):
        result = translate_phrase("send me 01712345678", "bn")
        self.assertEqual(result.quality, "phrase")
        self.assertIn("০১৭১২৩৪৫৬৭৮", result.translated)

    def test_unknown_text_is_not_translated(self):
        result = translate_phrase("quantum entanglement is fascinating", "bn")
        self.assertEqual(result.quality, "none")
        self.assertEqual(result.translated, "quantum entanglement is fascinating")

    def test_same_language_is_a_noop(self):
        result = translate_phrase("হ্যালো ভাই", "bn")
        self.assertEqual(result.quality, "none")
        self.assertEqual(result.translated, "হ্যালো ভাই")

    def test_longest_phrase_wins(self):
        # "security deposit" (2 words) must win over "deposit" (1 word).
        result = translate_phrase("I need the security deposit amount", "bn")
        self.assertEqual(result.quality, "phrase")
        self.assertIn("সিকিউরিটি ডিপোজিট", result.translated)


class ProviderTests(APITestCase):
    def test_default_provider_is_phrase(self):
        with override_settings(CHAT_TRANSLATE_PROVIDER="phrase"):
            result = translate("What is the monthly rent?", "bn")
            self.assertEqual(result.provider, "phrase")
            self.assertEqual(result.quality, "phrase")

    def test_http_gateway_success(self):
        fake = mock.Mock()
        fake.json.return_value = {"translated": "মাসিক ভাড়া কত?"}
        fake.raise_for_status = lambda: None
        with (
            override_settings(
                CHAT_TRANSLATE_PROVIDER="http",
                CHAT_TRANSLATE_GATEWAY_URL="https://translate.invalid/v1",
            ),
            mock.patch("requests.post", return_value=fake) as post,
        ):
            result = translate("What is the monthly rent?", "bn")
        self.assertEqual(result.provider, "http")
        self.assertEqual(result.quality, "full")
        self.assertEqual(result.translated, "মাসিক ভাড়া কত?")
        post.assert_called_once()

    def test_http_gateway_failure_falls_back_to_phrases(self):
        with (
            override_settings(
                CHAT_TRANSLATE_PROVIDER="http",
                CHAT_TRANSLATE_GATEWAY_URL="https://translate.invalid/v1",
            ),
            mock.patch("requests.post", side_effect=RuntimeError("gateway unreachable")),
        ):
            result = translate("What is the monthly rent?", "bn")
        self.assertEqual(result.provider, "phrase")
        self.assertEqual(result.quality, "phrase")

    def test_http_provider_without_gateway_url_falls_back(self):
        with override_settings(CHAT_TRANSLATE_PROVIDER="http", CHAT_TRANSLATE_GATEWAY_URL=""):
            result = translate("What is the monthly rent?", "bn")
        self.assertEqual(result.provider, "phrase")


class TranslateEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="translator", password="pass1234")

    def test_requires_authentication(self):
        response = self.client.post(
            "/api/v1/chat/translate/", {"text": "hello", "target": "bn"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_translates_known_phrase(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/chat/translate/",
            {"text": "What is the monthly rent?", "target": "bn"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quality"], "phrase")
        self.assertEqual(response.data["source_lang"], "en")
        self.assertIn("মাসিক ভাড়া", response.data["translated"])

    def test_unknown_text_reports_quality_none(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/chat/translate/",
            {"text": "quantum entanglement", "target": "bn"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["quality"], "none")
        self.assertEqual(response.data["translated"], "quantum entanglement")

    def test_missing_text_is_400(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/v1/chat/translate/", {"target": "bn"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bad_target_is_400(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/chat/translate/", {"text": "hello", "target": "fr"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(CHAT_TRANSLATE_ENABLED=False)
    def test_disabled_returns_403(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/v1/chat/translate/", {"text": "hello", "target": "bn"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CrossLingualSafetyTests(APITestCase):
    """The phrase core feeds the safety engine: Bengali payloads that the
    Bengali patterns alone miss must be caught via the normalized English
    scan. Detection-only — no DB involved."""

    def test_bangla_digit_payment_redirect_caught_via_normalization(self):
        # No Bengali pattern covers "পশ্চিম ইউনিয়ন" (western union) near a
        # Bangla-digit number; the normalized English version "western union
        # 01712345678" trips the EN scam_phrase pattern.
        content = "পশ্চিম ইউনিয়ন ০১৭১২৩৪৫৬৭৮"
        self.assertNotIn("scam_phrase", {h.key for h in detect(content)})
        assessment = assess_message(content)
        self.assertIn("scam_phrase", {h.key for h in assessment.hits})

    def test_bangla_impersonation_caught_via_normalization(self):
        # "আমি অ্যাডমিন" (I am admin) — the Bengali impersonation patterns only
        # cover Rentora-branded claims; the EN scan catches the generic claim.
        content = "আমি অ্যাডমিন"
        self.assertNotIn("impersonation", {h.key for h in detect(content)})
        assessment = assess_message(content)
        self.assertIn("impersonation", {h.key for h in assessment.hits})
        self.assertEqual(assessment.risk, "high")

    def test_western_union_bangla_caught_via_normalization(self):
        # No Bengali pattern covers "পশ্চিম ইউনিয়ন"; the EN scan catches it.
        content = "পশ্চিম ইউনিয়ন ফি"
        self.assertNotIn("scam_phrase", {h.key for h in detect(content)})
        assessment = assess_message(content)
        self.assertIn("scam_phrase", {h.key for h in assessment.hits})

    def test_english_messages_unaffected(self):
        assessment = assess_message("Hi, is the room still available?")
        self.assertEqual(assessment.risk, "low")
        self.assertEqual(assessment.hits, [])

    def test_bangla_benign_message_stays_clean(self):
        assessment = assess_message("মাসিক ভাড়া কত?")
        self.assertEqual(assessment.risk, "low")
