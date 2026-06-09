import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.models import BookingSession, Ticket

@pytest.fixture
def client():
    return TestClient(app)

def test_checkout_expired_reservation_fails(client, db_session):
    # 1. Create event
    event_payload = {
        "name": "Timeout Checkout Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Reserve 1 ticket
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    booking_res = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload).json()
    booking_id = booking_res["id"]

    # 4. Modify booking session expires_at in the database to be in the past
    db_session.expire_all()
    booking = db_session.get(BookingSession, booking_id)
    assert booking is not None
    booking.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    db_session.commit()

    # 5. Attempt checkout
    response = client.post(f"/api/bookings/{booking_id}/checkout")
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()

def test_expired_reservations_released_and_reclaimed(client, db_session):
    # 1. Create event
    event_payload = {
        "name": "Reclaimed Capacity Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 1
    tier_payload = {
        "name": "Single Ticket Tier",
        "price": 50.0,
        "capacity": 1
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Reserve 1 ticket (capacity is now fully taken)
    booking_res = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 1}).json()
    booking_id = booking_res["id"]

    # 4. Try reserving another ticket; should fail
    fail_res = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 1})
    assert fail_res.status_code == 400

    # 5. Modify booking session expires_at in the database to be in the past
    db_session.expire_all()
    booking = db_session.get(BookingSession, booking_id)
    assert booking is not None
    booking.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    db_session.commit()

    # 6. Run cleanup route
    cleanup_res = client.post("/api/bookings/cleanup")
    assert cleanup_res.status_code == 200
    assert cleanup_res.json()["cleaned_count"] == 1

    # 7. Check that tickets are deleted in database
    db_session.expire_all()
    tickets = db_session.query(Ticket).filter_by(booking_session_id=booking_id).all()
    assert len(tickets) == 0

    # 8. Reclaim capacity: reserving 1 ticket now succeeds
    success_res = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 1})
    assert success_res.status_code == 201

def test_checkout_just_before_expiry_success(client, db_session):
    # 1. Create event
    event_payload = {
        "name": "Just Before Expiry Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Reserve 1 ticket
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    booking_res = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload).json()
    booking_id = booking_res["id"]

    # 4. Modify booking session expires_at to be in the near future (e.g., +10 seconds)
    db_session.expire_all()
    booking = db_session.get(BookingSession, booking_id)
    assert booking is not None
    booking.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=10)
    db_session.commit()

    # 5. Attempt checkout (should succeed)
    response = client.post(f"/api/bookings/{booking_id}/checkout")
    assert response.status_code == 200

def test_double_cleanup_idempotent(client):
    # Call cleanup once
    res1 = client.post("/api/bookings/cleanup")
    assert res1.status_code == 200

    # Call cleanup a second time immediately
    res2 = client.post("/api/bookings/cleanup")
    assert res2.status_code == 200
