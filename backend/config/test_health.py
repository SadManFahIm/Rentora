"""Tests for health check and request correlation middleware (Phase 16)."""

from django.test import TestCase
from django.test.client import Client


class HealthCheckTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_returns_200(self):
        res = self.client.get("/health/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["db"], "ok")
        self.assertIn("uptime_seconds", data)
        self.assertIn("ts", data)

    def test_health_returns_json(self):
        res = self.client.get("/health/")
        self.assertEqual(res["Content-Type"], "application/json")

    def test_health_no_auth_required(self):
        """Health probe must work without authentication."""
        res = self.client.get("/health/")
        self.assertEqual(res.status_code, 200)


class RequestCorrelationTests(TestCase):
    def test_generates_request_id_when_not_provided(self):
        res = self.client.get("/health/")
        self.assertIn("X-Request-ID", res)

    def test_echoes_client_provided_request_id(self):
        res = self.client.get("/health/", HTTP_X_REQUEST_ID="my-trace-123")
        self.assertEqual(res["X-Request-ID"], "my-trace-123")

    def test_request_id_is_always_32_chars(self):
        res = self.client.get("/health/")
        rid = res["X-Request-ID"]
        self.assertEqual(len(rid), 32)
