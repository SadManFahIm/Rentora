"""Tests for Tier-5 funnel wiring — server-side conversion events.

The frontend emits page_view / room_view / chat_started / booking_requested;
the two steps that only happen server-side (a booking being approved, a
payment completing) must be recorded by the backend so the conversion funnel
reflects real conversion without trusting the client.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from analytics.models import Event
from analytics.services import record_event
from bookings.models import Booking
from rooms.models import Room

User = get_user_model()


def make_room(owner, **kw):
    defaults = dict(
        title="Funnel Room",
        description="A test room.",
        room_type="single",
        price=12000,
        area="Dhanmondi",
        address="Road 1",
        lat=23.7461,
        lng=90.3762,
        amenities=["wifi"],
        size_sqft=300,
    )
    defaults.update(kw)
    return Room.objects.create(owner=owner, **defaults)


class RecordEventHelperTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="funnel_user", password="test12345")

    def test_record_event_authenticated_attributes_user(self):
        record_event(self.user, "booking_confirmed", category="booking")
        event = Event.objects.get(event="booking_confirmed")
        self.assertEqual(event.user_id, self.user.pk)
        self.assertEqual(event.category, "booking")

    def test_record_event_anonymous_keeps_user_none(self):
        record_event(None, "payment_completed", properties={"amount": "1000"})
        event = Event.objects.get(event="payment_completed")
        self.assertIsNone(event.user)
        self.assertEqual(event.properties, {"amount": "1000"})


class BookingConfirmedEventTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="funnel_owner", password="test12345")
        self.tenant = User.objects.create_user(
            username="funnel_tenant", email="t@example.com", password="test12345"
        )
        self.room = make_room(self.owner)

    def test_approving_booking_emits_confirmed_event_for_tenant(self):
        booking = Booking.objects.create(
            room=self.room, tenant=self.tenant, check_in=date(2026, 9, 1), monthly_rent=12000
        )
        booking.status = Booking.Status.APPROVED
        booking.save()

        event = Event.objects.get(event="booking_confirmed")
        self.assertEqual(event.user_id, self.tenant.pk)
        self.assertEqual(event.properties["room_id"], self.room.pk)
        self.assertEqual(event.properties["booking_id"], booking.pk)

    def test_pending_booking_emits_no_confirmed_event(self):
        Booking.objects.create(
            room=self.room, tenant=self.tenant, check_in=date(2026, 9, 1), monthly_rent=12000
        )
        self.assertFalse(Event.objects.filter(event="booking_confirmed").exists())
