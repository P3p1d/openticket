import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.models import TicketTier

@pytest.fixture
def client():
    return TestClient(app)

def test_reserve_exactly_capacity(client):
    # 1. Create event
    event_payload = {
        "name": "Exact Capacity Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 5
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Reserve exactly 5 tickets
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 5
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload)
    assert response.status_code == 201
    assert response.json()["quantity"] == 5

def test_reserve_exceeding_capacity_by_one_fails(client):
    # 1. Create event
    event_payload = {
        "name": "Exceed Capacity Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 5
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Try to reserve 6 tickets
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 6
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload)
    assert response.status_code == 400

def test_reserve_when_capacity_is_zero_fails(client, db_session):
    # 1. Create event
    event_payload = {
        "name": "Zero Capacity Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 1
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 1
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. Manually update capacity to 0 in database
    db_session.expire_all()
    tier = db_session.get(TicketTier, tier_id)
    assert tier is not None
    tier.capacity = 0
    db_session.commit()

    # 4. Reserve 1 ticket, which should fail because capacity is 0
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload)
    assert response.status_code == 400

def test_multiple_reserves_summing_exactly_to_capacity(client):
    # 1. Create event
    event_payload = {
        "name": "Multiple Reserves Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 5
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. First reserve 2
    res1 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 2})
    assert res1.status_code == 201

    # 4. Second reserve 3 (total 5)
    res2 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 3})
    assert res2.status_code == 201

def test_multiple_reserves_exceeding_capacity_fails(client):
    # 1. Create event
    event_payload = {
        "name": "Exceeding Sum Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_id = client.post("/api/events", json=event_payload).json()["id"]

    # 2. Create tier with capacity 5
    tier_payload = {
        "name": "Standard Ticket",
        "price": 20.0,
        "capacity": 5
    }
    tier_id = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()["id"]

    # 3. First reserve 3
    res1 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 3})
    assert res1.status_code == 201

    # 4. Second reserve 3 (total 6 > 5) should fail
    res2 = client.post(f"/api/events/{event_id}/reserve", json={"tier_id": tier_id, "quantity": 3})
    assert res2.status_code == 400
