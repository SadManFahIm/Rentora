"""Tests for the OSRM commute-ETA layer (Tier 2).

The network call is patched (rooms.osrm._http_get) so the suite is hermetic
and fast; the fallback path (routing down → straight-line heuristic) is the
behaviour that must never regress.
"""

import types
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from rooms import osrm as osrm_module
from rooms.map_intel import commute_eta


def _fake_response(duration=600.0, distance=5000.0):
    return types.SimpleNamespace(
        json=lambda: {"routes": [{"duration": duration, "distance": distance}]},
        raise_for_status=lambda: None,
    )


class OsrmRouteTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_route_returns_duration_and_distance(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", return_value=_fake_response()),
        ):
            result = osrm_module.osrm_route(23.8, 90.4, 23.9, 90.5)
        self.assertEqual(result, {"duration": 600.0, "distance": 5000.0})

    def test_route_is_cached(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", return_value=_fake_response()) as http,
        ):
            osrm_module.osrm_route(23.8, 90.4, 23.9, 90.5)
            osrm_module.osrm_route(23.8, 90.4, 23.9, 90.5)
        self.assertEqual(http.call_count, 1)

    def test_route_returns_none_on_failure(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", side_effect=Exception("routing down")),
        ):
            self.assertIsNone(osrm_module.osrm_route(23.8, 90.4, 23.9, 90.5))

    def test_disabled_flag_returns_none_without_network(self):
        with (
            override_settings(OSRM_ENABLED=False),
            mock.patch.object(osrm_module, "_http_get") as http,
        ):
            self.assertIsNone(osrm_module.osrm_route(23.8, 90.4, 23.9, 90.5))
        http.assert_not_called()


class OsrmEtaTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_car_minutes_and_cng_factor(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", return_value=_fake_response()),
        ):
            car = osrm_module.osrm_eta(23.8, 90.4, 23.9, 90.5, "car")
            self.assertEqual(car["minutes"], 10)  # 600s -> 10 min
            self.assertEqual(car["distance_km"], 5.0)
            self.assertEqual(car["source"], "osrm")
            cng = osrm_module.osrm_eta(23.8, 90.4, 23.9, 90.5, "cng")
            self.assertEqual(cng["minutes"], 12)  # car x 1.2 congestion factor

    def test_commute_eta_uses_osrm_when_available(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", return_value=_fake_response()),
        ):
            eta = commute_eta(23.8, 90.4, 23.9, 90.5, "driving")
        self.assertEqual(eta.minutes, 10)
        self.assertIn("OSRM", eta.detail)

    def test_commute_eta_falls_back_to_heuristic_when_osrm_down(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", side_effect=Exception("down")),
        ):
            eta = commute_eta(23.8, 90.4, 23.9, 90.5, "driving")
        self.assertIsNotNone(eta.minutes)
        self.assertNotIn("OSRM", eta.detail)
        self.assertTrue(eta.estimate)


class OsrmEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("commute-eta")

    def test_eta_endpoint_returns_osrm_source(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", return_value=_fake_response()),
        ):
            response = self.client.get(
                self.url,
                {"from_lat": 23.8, "from_lng": 90.4, "to_lat": 23.9, "to_lng": 90.5, "mode": "car"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "osrm")
        self.assertEqual(response.data["minutes"], 10)

    def test_eta_endpoint_falls_back_gracefully(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get", side_effect=Exception("down")),
        ):
            response = self.client.get(
                self.url,
                {"from_lat": 23.8, "from_lng": 90.4, "to_lat": 23.9, "to_lng": 90.5, "mode": "car"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "heuristic")
        self.assertIsNotNone(response.data["minutes"])

    def test_missing_coords_400(self):
        response = self.client.get(self.url, {"mode": "car"})
        self.assertEqual(response.status_code, 400)

    def test_unknown_mode_400(self):
        response = self.client.get(
            self.url,
            {"from_lat": 1, "from_lng": 2, "to_lat": 3, "to_lng": 4, "mode": "teleport"},
        )
        self.assertEqual(response.status_code, 400)

    def test_walking_uses_heuristic_without_osrm(self):
        with (
            override_settings(OSRM_ENABLED=True),
            mock.patch.object(osrm_module, "_http_get") as http,
        ):
            response = self.client.get(
                self.url,
                {
                    "from_lat": 23.8,
                    "from_lng": 90.4,
                    "to_lat": 23.9,
                    "to_lng": 90.5,
                    "mode": "walking",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "heuristic")
        http.assert_not_called()
