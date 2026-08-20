"""Feature-flag tests (targeting, rollout, disabled behaviour, admin API)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import FeatureFlag, is_enabled

User = get_user_model()


@override_settings(ENV_NAME="dev")
class FeatureFlagLogicTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="flag_user", email="flag_user@example.com", password="test12345"
        )

    def test_missing_flag_is_disabled(self):
        self.assertFalse(is_enabled("does.not.exist", user=self.user))

    def test_enabled_flag_for_everyone(self):
        FeatureFlag.objects.create(
            key="phase16.semantic_search", status="enabled", rollout_percentage=100
        )
        self.assertTrue(is_enabled("phase16.semantic_search", user=self.user))

    def test_disabled_flag_is_never_on(self):
        FeatureFlag.objects.create(
            key="phase16.vector_search", status="disabled", rollout_percentage=100
        )
        self.assertFalse(is_enabled("phase16.vector_search", user=self.user))

    def test_environment_targeting(self):
        FeatureFlag.objects.create(
            key="env.flag", status="enabled", rollout_percentage=100, environments=["prod"]
        )
        self.assertFalse(is_enabled("env.flag", user=self.user))  # dev env

    def test_role_targeting(self):
        tenant = User.objects.create_user(
            username="flag_tenant", email="flag_tenant@example.com", password="test12345"
        )
        broker = User.objects.create_user(
            username="flag_broker",
            email="flag_broker@example.com",
            password="test12345",
            role="broker",
        )
        FeatureFlag.objects.create(
            key="role.flag", status="enabled", rollout_percentage=100, roles=["broker"]
        )
        self.assertTrue(is_enabled("role.flag", user=broker))
        self.assertFalse(is_enabled("role.flag", user=tenant))

    def test_percentage_rollout_deterministic(self):
        FeatureFlag.objects.create(
            key="rollout.flag", status="partial", rollout_percentage=0, environments=[]
        )
        # 0% rollout never enables.
        self.assertFalse(is_enabled("rollout.flag", user=self.user))
        self.assertFalse(is_enabled("rollout.flag", user=self.user))

    def test_explicit_user_allowlist(self):
        other = User.objects.create_user(
            username="flag_other", email="flag_other@example.com", password="test12345"
        )
        FeatureFlag.objects.create(
            key="userlist.flag",
            status="enabled",
            rollout_percentage=100,
            user_ids=[self.user.id],
        )
        self.assertTrue(is_enabled("userlist.flag", user=self.user))
        self.assertFalse(is_enabled("userlist.flag", user=other))

    def test_percentage_distribution(self):
        FeatureFlag.objects.create(
            key="spread.flag", status="partial", rollout_percentage=50, environments=[]
        )
        hits = sum(is_enabled("spread.flag", user=None, anonymous_id=str(i)) for i in range(200))
        # With 50% rollout across 200 deterministic buckets it should be ~100.
        self.assertGreater(hits, 60)
        self.assertLess(hits, 140)


class FeatureFlagApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="flag_admin", email="flag_admin@example.com", password="test12345"
        )
        self.user = User.objects.create_user(
            username="flag_normal", email="flag_normal@example.com", password="test12345"
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_list_and_update(self):
        FeatureFlag.objects.create(
            key="phase16.optimized_images", status="disabled", rollout_percentage=0
        )
        resp = self.client.get("/api/v1/flags/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(any(f["key"] == "phase16.optimized_images" for f in resp.data))

        resp = self.client.patch(
            "/api/v1/flags/phase16.optimized_images/", {"status": "enabled"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "enabled")
        self.assertTrue(is_enabled("phase16.optimized_images", user=self.user))

    def test_non_admin_cannot_read(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/v1/flags/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
