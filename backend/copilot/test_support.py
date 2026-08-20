"""Phase 15 (B2) — AI Support Copilot tests.

Covers deterministic bilingual retrieval, live-fact rendering (tier prices),
the transparent ungrounded fallback, and the public REST endpoint.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from .support import support_answer


class SupportRetrievalTests(APITestCase):
    def test_english_listing_question(self):
        result = support_answer("How do I list my room?")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["topic"], "listing_howto")
        self.assertIn("dashboard", result["answer"])

    def test_bangla_listing_question(self):
        result = support_answer("কীভাবে রুম লিস্ট করব?")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["topic"], "listing_howto")
        self.assertTrue(result["answer_bn"])

    def test_booking_question(self):
        result = support_answer("How does booking work?")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["topic"], "booking_howto")

    def test_kyc_question(self):
        result = support_answer("NID verification কেমন হয়?")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["topic"], "kyc")

    def test_unknown_question_falls_back_transparently(self):
        result = support_answer("what is the meaning of life")
        self.assertFalse(result["grounded"])
        self.assertEqual(result["topic"], "general")
        self.assertTrue(result["answer_bn"])

    def test_question_and_answer_are_bilingual(self):
        result = support_answer("How do I list my room?")
        self.assertTrue(result["title"])
        self.assertTrue(result["title_bn"])
        self.assertTrue(result["answer"])
        self.assertTrue(result["answer_bn"])


class SupportDynamicFactTests(APITestCase):
    def test_tier_prices_are_live(self):
        result = support_answer("What does premium promotion cost?")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["topic"], "pricing_tiers")
        # Grounded in settings.LISTING_TIER_PRICING — the real prices.
        self.assertIn("199", result["answer"])
        self.assertIn("499", result["answer"])

    def test_tier_duration_is_live(self):
        result = support_answer("how long does featured last")
        self.assertEqual(result["topic"], "pricing_tiers")
        self.assertIn("30 days", result["answer"])


class SupportEndpointTests(APITestCase):
    def test_endpoint_is_public(self):
        response = self.client.post(
            "/api/v1/copilot/support/", {"message": "how do I list my room?"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["grounded"])
        self.assertEqual(response.data["topic"], "listing_howto")

    def test_endpoint_returns_bangla_answer(self):
        response = self.client.post(
            "/api/v1/copilot/support/", {"message": "কীভাবে রুম লিস্ট করব?"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["answer_bn"])

    def test_endpoint_ungrounded_fallback(self):
        response = self.client.post(
            "/api/v1/copilot/support/", {"message": "random gibberish xyz"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["grounded"])

    def test_empty_message_is_400(self):
        response = self.client.post("/api/v1/copilot/support/", {"message": ""}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
