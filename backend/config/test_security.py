"""Tier-1 quick win — security headers + security.txt.

Verifies every response carries the hardening headers (CSP, nosniff,
Referrer-Policy, Permissions-Policy), HSTS only appears when configured,
and RFC 9116 security.txt is served at both paths with no secrets.
"""

from django.test import TestCase, override_settings


class SecurityHeadersTests(TestCase):
    def test_api_response_carries_hardening_headers(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        self.assertEqual(res["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(res["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")
        csp = res["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_no_hsts_in_dev(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertNotIn("Strict-Transport-Security", res)

    @override_settings(SECURE_HSTS_SECONDS=31536000)
    def test_hsts_when_configured(self):
        res = self.client.get("/api/v1/rooms/")
        self.assertEqual(res["Strict-Transport-Security"], "max-age=31536000")


class SecurityTxtTests(TestCase):
    def test_well_known_path_serves_plain_text_policy(self):
        res = self.client.get("/.well-known/security.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res["Content-Type"])
        body = res.content.decode()
        self.assertIn("Contact:", body)
        self.assertIn("Policy:", body)

    def test_convenience_path_also_serves(self):
        res = self.client.get("/security.txt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Contact:", res.content.decode())

    def test_policy_contains_no_secrets(self):
        res = self.client.get("/.well-known/security.txt")
        body = res.content.decode().lower()
        for secret_word in ("password", "secret_key", "api_key", "token=", "private key"):
            self.assertNotIn(secret_word, body)
