"""Tests for client-IP resolution behind proxies (config/ip.py, Phase 16)."""

from types import SimpleNamespace

from django.test import TestCase, override_settings

from config.ip import get_client_ip
from config.throttling import TrustedAnonRateThrottle


def _request(remote_addr: str, xff: str | None = None):
    meta = {"REMOTE_ADDR": remote_addr}
    if xff is not None:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    return SimpleNamespace(META=meta)


class GetClientIpTests(TestCase):
    @override_settings(NUM_PROXIES=0)
    def test_default_ignores_xff(self):
        """No trust configured -> XFF is never parsed (anti-spoofing)."""
        req = _request("10.0.0.1", "1.2.3.4, 5.6.7.8")
        self.assertEqual(get_client_ip(req), "10.0.0.1")

    @override_settings(NUM_PROXIES=0)
    def test_default_without_xff(self):
        self.assertEqual(get_client_ip(_request("10.0.0.1")), "10.0.0.1")

    @override_settings(NUM_PROXIES=1)
    def test_single_proxy_uses_rightmost(self):
        """Behind one trusted LB, the rightmost XFF value is the real client
        (appended by the LB); any spoofed prefix is ignored."""
        req = _request("10.0.0.9", "1.2.3.4, 5.6.7.8")
        self.assertEqual(get_client_ip(req), "5.6.7.8")

    @override_settings(NUM_PROXIES=1)
    def test_single_proxy_single_entry(self):
        self.assertEqual(get_client_ip(_request("10.0.0.9", "1.2.3.4")), "1.2.3.4")

    @override_settings(NUM_PROXIES=2)
    def test_two_proxies_skips_two_rightmost(self):
        """Chain client -> P1 -> P2 -> origin (XFF = client, P1) -> client."""
        req = _request("10.0.0.9", "1.2.3.4, 5.6.7.8, 9.9.9.9")
        self.assertEqual(get_client_ip(req), "5.6.7.8")

    @override_settings(NUM_PROXIES=3)
    def test_proxies_exceeding_header_fall_back_to_leftmost(self):
        req = _request("10.0.0.9", "1.2.3.4")
        self.assertEqual(get_client_ip(req), "1.2.3.4")

    @override_settings(NUM_PROXIES=1)
    def test_no_xff_falls_back_to_remote_addr(self):
        self.assertEqual(get_client_ip(_request("10.0.0.9")), "10.0.0.9")


class TrustedThrottleIdentTests(TestCase):
    @override_settings(NUM_PROXIES=1)
    def test_throttle_ident_resolves_via_proxy(self):
        req = _request("10.0.0.9", "1.2.3.4, 5.6.7.8")
        throttle = TrustedAnonRateThrottle()
        self.assertEqual(throttle.get_ident(req), "5.6.7.8")

    @override_settings(NUM_PROXIES=0)
    def test_throttle_ident_without_proxy_uses_remote_addr(self):
        req = _request("10.0.0.9", "1.2.3.4, 5.6.7.8")
        throttle = TrustedAnonRateThrottle()
        self.assertEqual(throttle.get_ident(req), "10.0.0.9")
