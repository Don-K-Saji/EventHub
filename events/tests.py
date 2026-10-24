from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Event, Reservation


class EventHubAPITests(APITestCase):
    def setUp(self):
        self.event1 = Event.objects.create(
            title="PyCon India 2025",
            venue="NIMHANS Convention Centre, Bangalore",
            date="2025-09-20",
            total_seats=500,
            available_seats=500,
            status="upcoming",
        )
        self.event2 = Event.objects.create(
            title="DjangoCon 2025",
            venue="KTPO Whitefield, Bangalore",
            date="2025-11-15",
            total_seats=300,
            available_seats=300,
            status="completed",
        )

    # 1. Create an event
    def test_create_event_success(self):
        url = reverse('event-list')
        data = {
            "title": "React Summit 2025",
            "venue": "BIEC, Bangalore",
            "date": "2025-10-10",
            "total_seats": 200,
            "available_seats": 200,
            "status": "upcoming",
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], "React Summit 2025")
        self.assertEqual(response.data['reservations_count'], 0)
        self.assertEqual(Event.objects.count(), 3)

    # Validation: available_seats cannot exceed total_seats
    def test_create_event_invalid_available_seats(self):
        url = reverse('event-list')
        data = {
            "title": "Invalid Event",
            "venue": "Online",
            "date": "2025-12-01",
            "total_seats": 100,
            "available_seats": 150,
            "status": "upcoming",
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('available_seats cannot exceed total_seats.', str(response.data))

    # 2. List all events
    def test_list_events(self):
        url = reverse('event-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    # 3. Filter events by status
    def test_filter_events_by_status(self):
        url = f"{reverse('event-list')}?status=upcoming"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "PyCon India 2025")

        url_completed = f"{reverse('event-list')}?status=completed"
        response_completed = self.client.get(url_completed)
        self.assertEqual(response_completed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_completed.data), 1)
        self.assertEqual(response_completed.data[0]['title'], "DjangoCon 2025")

    # 4. Filter events by venue
    def test_filter_events_by_venue(self):
        url = f"{reverse('event-list')}?venue=nimhans"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "PyCon India 2025")

    # 5. Create a reservation (seats deducted from event)
    def test_create_reservation_success(self):
        url = reverse('reservation-list')
        data = {
            "event": self.event1.id,
            "attendee_name": "Priya Sharma",
            "attendee_email": "priya@example.com",
            "seats_reserved": 2,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'confirmed')
        self.assertEqual(response.data['seats_reserved'], 2)

        # Verify seats were deducted from event
        self.event1.refresh_from_db()
        self.assertEqual(self.event1.available_seats, 498)

        # Verify reservations_count computed field
        event_response = self.client.get(reverse('event-detail', args=[self.event1.id]))
        self.assertEqual(event_response.data['reservations_count'], 1)

    # 6. Overbooking attempt returns 400
    def test_reservation_overbooking_returns_400(self):
        self.event1.available_seats = 1
        self.event1.save()

        url = reverse('reservation-list')
        data = {
            "event": self.event1.id,
            "attendee_name": "Rahul Verma",
            "attendee_email": "rahul@example.com",
            "seats_reserved": 2,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only 1 seat(s) available.", str(response.data))

    # Reserving less than 1 seat returns 400
    def test_reservation_invalid_seat_count(self):
        url = reverse('reservation-list')
        data = {
            "event": self.event1.id,
            "attendee_name": "Amit Patel",
            "attendee_email": "amit@example.com",
            "seats_reserved": 0,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Must reserve at least 1 seat.', str(response.data))

    # Reserving for non-active event returns 400
    def test_reservation_for_completed_event(self):
        url = reverse('reservation-list')
        data = {
            "event": self.event2.id,  # status is 'completed'
            "attendee_name": "Neha Gupta",
            "attendee_email": "neha@example.com",
            "seats_reserved": 1,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot reserve seats for a completed event.', str(response.data))

    # 7. Cancel a reservation (seats restored to event)
    def test_cancel_reservation_success(self):
        reservation = Reservation.objects.create(
            event=self.event1,
            attendee_name="Priya Sharma",
            attendee_email="priya@example.com",
            seats_reserved=2,
            status='confirmed',
        )
        self.event1.available_seats -= 2
        self.event1.save()

        cancel_url = reverse('reservation-cancel', args=[reservation.id])
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')

        # Verify seats were restored
        self.event1.refresh_from_db()
        self.assertEqual(self.event1.available_seats, 500)

        # Cancel again returns 400
        response_again = self.client.post(cancel_url)
        self.assertEqual(response_again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response_again.data, {'error': 'Already cancelled.'})

    # 8. Filter reservations by event_id
    def test_filter_reservations_by_event_id(self):
        res1 = Reservation.objects.create(
            event=self.event1,
            attendee_name="User 1",
            attendee_email="user1@example.com",
            seats_reserved=1,
            status='confirmed',
        )
        res2 = Reservation.objects.create(
            event=self.event2,
            attendee_name="User 2",
            attendee_email="user2@example.com",
            seats_reserved=1,
            status='confirmed',
        )

        url = f"{reverse('reservation-list')}?event_id={self.event1.id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['attendee_name'], "User 1")
