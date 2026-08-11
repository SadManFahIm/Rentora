"""Tests for Web Push subscriptions and delivery guard (Phase 10)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import PushSubscription
from notifications.webpush import send_push, send_push_to_user

User = get_user_model()

ENDPOINT = "https://fcm.googleapis.com/fcm/send/fake-device-token-123"


class PushSubscriptionAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pushuser", email="push@example.com", password="test12345"
        )
        self.client.force_authenticate(self.user)

    def test_subscribe_unsubscribe(self):
        res = self.client.post(
            "/api/v1/notifications/push/subscribe/",
            {"endpoint": ENDPOINT, "auth": "aaa", "p256dh": "bbb"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

        # Idempotent re-subscribe updates rather than duplicates.
        again = self.client.post(
            "/api/v1/notifications/push/subscribe/",
            {"endpoint": ENDPOINT, "auth": "aaa2", "p256dh": "bbb2"},
            format="json",
        )
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

        deleted = self.client.delete(
            "/api/v1/notifications/push/subscribe/",
            {"endpoint": ENDPOINT},
            format="json",
        )
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 0)

    def test_subscribe_requires_all_fields(self):
        res = self.client.post(
            "/api/v1/notifications/push/subscribe/",
            {"endpoint": ENDPOINT},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        res = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class SendPushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pushuser2", email="push2@example.com", password="test12345"
        )
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint=ENDPOINT,
            auth="aaa",
            p256dh="bbb",
        )

    @override_settings(VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="")
    def test_no_vapid_is_safe_noop(self):
        self.assertFalse(send_push(self.subscription, "t", "b"))
        self.assertEqual(send_push_to_user(self.user, "t", "b"), 0)

    @override_settings(
        VAPID_PRIVATE_KEY="priv", VAPID_PUBLIC_KEY="pub", VAPID_SUBJECT="mailto:a@b.com"
    )
    def test_dead_subscription_is_removed(self):
        from pywebpush import WebPushException

        def _boom(*args, **kwargs):
            exc = WebPushException("gone")
            exc.response = type("R", (), {"status_code": 410})()
            raise exc

        with patch("notifications.webpush.webpush", side_effect=_boom):
            result = send_push(self.subscription, "t", "b")
        self.assertFalse(result)
        self.assertFalse(PushSubscription.objects.filter(pk=self.subscription.pk).exists())
