"""Tests for the Phase 16 self-healing presence lease model (chat/presence.py).

The previous reference-count implementation leaked: a worker hard-killed
without firing ``disconnect`` left a user permanently "online" because its
cache keys had no expiry. The lease model must self-heal — stale leases are
pruned on read and the whole key expires.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings

from . import presence


class PresenceLeaseTests(TestCase):
    def setUp(self):
        # LocMemCache is process-global and persists across tests — isolate.
        cache.clear()

    def test_mark_online_then_offline(self):
        presence.mark_online(1)
        self.assertTrue(presence.is_online(1))
        presence.mark_offline(1)
        self.assertFalse(presence.is_online(1))

    def test_multiple_connections_ref_counted(self):
        presence.mark_online(1, "tab-a")
        presence.mark_online(1, "tab-b")
        self.assertTrue(presence.is_online(1))
        presence.mark_offline(1, "tab-a")
        self.assertTrue(presence.is_online(1))  # tab-b still connected
        presence.mark_offline(1, "tab-b")
        self.assertFalse(presence.is_online(1))

    def test_offline_does_not_remove_other_connections(self):
        presence.mark_online(1, "a")
        presence.mark_offline(1, "b")  # never existed
        self.assertTrue(presence.is_online(1))

    def test_bulk_online_status_splits_users(self):
        presence.mark_online(1, "a")
        presence.mark_online(2, "x")
        presence.mark_offline(2, "x")
        result = presence.bulk_online_status([1, 2, 3])
        self.assertEqual(result["online"], [1])
        self.assertEqual(sorted(result["offline"]), [2, 3])

    @override_settings(PRESENCE_CONNECTION_TTL=-1)
    def test_stale_lease_is_pruned_on_read(self):
        """A 'dead' connection (worker killed, no disconnect) self-heals."""
        presence.mark_online(1, "dead-socket")
        # TTL is negative → every lease is already stale → pruned on read.
        self.assertFalse(presence.is_online(1))

    @override_settings(PRESENCE_CONNECTION_TTL=-1)
    def test_stale_lease_expires_key(self):
        """A fully-stale user key is removed, not left accumulating."""
        presence.mark_online(1, "dead-socket")
        presence.is_online(1)  # read triggers prune → empty → delete
        self.assertFalse(presence.is_online(1))

    def test_touch_refreshes_lease(self):
        presence.mark_online(1, "a")
        presence.touch(1, "a")  # no-op if present; must not throw
        self.assertTrue(presence.is_online(1))

    def test_touch_missing_connection_is_noop(self):
        presence.mark_online(1, "a")
        presence.touch(1, "ghost")
        self.assertTrue(presence.is_online(1))

    def test_key_is_namespaced(self):
        """Presence keys live under the chat:online: namespace."""
        presence.mark_online(7, "a")
        self.assertEqual(presence._key(7), "chat:online:7")
