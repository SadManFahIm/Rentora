"""Tests for saved searches — API CRUD, manual check, daily digest task."""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import Notification
from rooms.models import Room

User = get_user_model()


class SavedSearchAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="saver", email="saver@example.com", password="test12345"
        )
        self.landlord = User.objects.create_user(
            username="owner1", email="owner1@example.com", password="test12345"
        )
        self._make_room("Mirpur Studio", "Mirpur", 9000, room_type="studio")
        self.client.force_authenticate(self.user)

    def _make_room(self, title, area, price, room_type="single"):
        return Room.objects.create(
            owner=self.landlord,
            title=title,
            description="A cozy room near university.",
            room_type=room_type,
            price=price,
            area=area,
            address="12 Road",
            lat=23.8,
            lng=90.4,
            amenities=["wifi"],
            size_sqft=250,
        )

    def _save(self, **filters):
        return self.client.post(
            "/api/v1/saved-searches/",
            {"name": "My search", "filters": filters},
            format="json",
        )

    def test_create_list_delete(self):
        res = self._save(area="Mirpur", price_max=10000)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        search_id = res.data["id"]

        listed = self.client.get("/api/v1/saved-searches/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.data["count"], 1)

        deleted = self.client.delete(f"/api/v1/saved-searches/{search_id}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get("/api/v1/saved-searches/").data["count"], 0)

    def test_check_reports_new_matches_and_advances_last_checked(self):
        res = self._save(area="Mirpur")
        search_id = res.data["id"]
        self.assertIsNone(res.data["last_checked_at"])

        checked = self.client.post(f"/api/v1/saved-searches/{search_id}/check/")
        self.assertEqual(checked.status_code, status.HTTP_200_OK)
        # Room created in setUp counts as "new since first check" (24h window).
        self.assertEqual(checked.data["new_matches"], 1)

        refreshed = self.client.get("/api/v1/saved-searches/").data["results"][0]
        self.assertIsNotNone(refreshed["last_checked_at"])

        # A room created after the check is the only new match next time.
        old_id = Room.objects.first().id
        Room.objects.filter(pk=old_id).update(
            created_at=timezone.now() - timezone.timedelta(days=2)
        )
        checked_again = self.client.post(f"/api/v1/saved-searches/{search_id}/check/")
        self.assertEqual(checked_again.data["new_matches"], 0)

    def test_requires_auth(self):
        self.client.force_authenticate(None)
        res = self.client.get("/api/v1/saved-searches/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class SavedSearchDigestTaskTests(APITestCase):
    def test_task_alerts_new_matches(self):
        from datetime import timedelta

        user = User.objects.create_user(
            username="saver2", email="saver2@example.com", password="test12345"
        )
        landlord = User.objects.create_user(
            username="owner2", email="owner2@example.com", password="test12345"
        )
        from savedsearches.models import SavedSearch

        SavedSearch.objects.create(
            user=user,
            name="Mirpur rooms",
            filters={"area": "Mirpur", "price_max": 12000},
            last_checked_at=timezone.now() - timedelta(days=1),
        )
        Room.objects.create(
            owner=landlord,
            title="New Mirpur Flat",
            description="Fresh listing.",
            room_type="single",
            price=10000,
            area="Mirpur",
            address="x",
            lat=23.8,
            lng=90.4,
            amenities=["wifi"],
            size_sqft=220,
        )

        from savedsearches.tasks import check_saved_searches

        result = check_saved_searches()
        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["alerted"], 1)
        notification = Notification.objects.get(user=user)
        self.assertEqual(notification.notification_type, Notification.Type.SAVED_SEARCH_MATCH)
        self.assertIn("New Mirpur Flat", notification.message)

        # Second run: nothing new (last_checked_at advanced) -> no alert.
        second = check_saved_searches()
        self.assertEqual(second["alerted"], 0)
