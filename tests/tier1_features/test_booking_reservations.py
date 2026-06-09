import pytest
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def event_and_tier(client):
    event_payload = {
        "name": "Booking Reservations Event",
        "description": "For testing reservations.",
        "date": "2026-06-21T21:00:00",
        "location": "Dark Ambient Vault"
    }
    event_res = client.post("/api/events", json=event_payload).json()
    event_id = event_res["id"]
    
    tier_payload = {
        "name": "Limited VIP",
        "price": 80.0,
        "capacity": 5
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()
    tier_id = tier_res["id"]
    
    return event_id, tier_id

def test_reserve_tickets_success(client, event_and_tier):
    event_id, tier_id = event_and_tier
    payload = {
        "tier_id": tier_id,
        "quantity": 2
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "reserved"
    assert data["quantity"] == 2
    assert len(data["tickets"]) == 2
    assert "id" in data
    assert "booking_session_id" in data
    assert data["booking_session_id"] == data["id"]

def test_reserve_tickets_insufficient_capacity_fails(client, event_and_tier):
    event_id, tier_id = event_and_tier
    # Capacity is 5. Try to reserve 6.
    payload = {
        "tier_id": tier_id,
        "quantity": 6
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=payload)
    assert response.status_code == 400
    assert "capacity" in response.json()["detail"].lower()

def test_reserve_tickets_invalid_tier_404(client, event_and_tier):
    event_id, _ = event_and_tier
    payload = {
        "tier_id": 999999,
        "quantity": 1
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=payload)
    assert response.status_code == 404

def test_reserve_tickets_zero_quantity_fails(client, event_and_tier):
    event_id, tier_id = event_and_tier
    payload = {
        "tier_id": tier_id,
        "quantity": 0
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=payload)
    assert response.status_code == 422

def test_reservation_capacity_decrement_reflected(client, event_and_tier):
    event_id, tier_id = event_and_tier
    # Capacity is 5.
    # Reserve 3.
    res1 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 3})
    assert res1.status_code == 201
    
    # Try to reserve 3 more. 3 + 3 = 6 > 5. Should fail.
    res2 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 3})
    assert res2.status_code == 400
    
    # Reserve exactly 2 (the remaining capacity).
    res3 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 2})
    assert res3.status_code == 201
