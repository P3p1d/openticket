import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_create_event_long_name(client):
    # Name is 101 characters long (exceeds the max_length=100 constraint)
    payload = {
        "name": "E" * 101,
        "description": "Validation testing for long name.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    response = client.post("/api/events", json=payload)
    assert response.status_code == 422

def test_create_event_past_date(client):
    # Date is in the past
    payload = {
        "name": "Past Event",
        "description": "Validation testing for past date.",
        "date": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    response = client.post("/api/events", json=payload)
    assert response.status_code == 422

def test_create_tier_negative_price_fails(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for Tier Price Test",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create tier with negative price
    tier_payload = {
        "name": "Standard Ticket",
        "price": -10.0,
        "capacity": 100
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert response.status_code == 422

def test_create_tier_zero_price_success(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Free Event",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create tier with zero price
    tier_payload = {
        "name": "Free Ticket",
        "price": 0.0,
        "capacity": 100
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert response.status_code == 201
    assert response.json()["price"] == 0.0

def test_create_tier_negative_capacity_fails(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for Capacity Test",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create tier with negative capacity
    tier_payload = {
        "name": "Negative Capacity",
        "price": 15.0,
        "capacity": -10
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert response.status_code == 422

def test_create_tier_zero_capacity_fails(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for Zero Capacity Test",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create tier with zero capacity
    tier_payload = {
        "name": "Zero Capacity",
        "price": 15.0,
        "capacity": 0
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert response.status_code == 422

def test_reserve_tickets_negative_quantity_fails(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for Reserve Quantity Test",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create a valid tier
    tier_payload = {
        "name": "Regular Ticket",
        "price": 20.0,
        "capacity": 10
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert tier_res.status_code == 201
    tier_id = tier_res.json()["id"]

    # 3. Reserve negative quantity
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": -1
    }
    response = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload)
    assert response.status_code == 422

def test_reserve_tickets_non_existent_event_404(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for 404 Event Reserve Test",
        "description": "Valid event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create a valid tier
    tier_payload = {
        "name": "Regular Ticket",
        "price": 20.0,
        "capacity": 10
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert tier_res.status_code == 201
    tier_id = tier_res.json()["id"]

    # 3. Reserve tickets on non-existent event ID 999999
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    response = client.post("/api/events/999999/reserve", json=reserve_payload)
    assert response.status_code == 404

def test_reserve_tickets_mismatched_event_tier_400(client):
    # 1. Create event 1 and tier
    event1_payload = {
        "name": "Event One",
        "description": "Valid event 1.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event1_res = client.post("/api/events", json=event1_payload)
    assert event1_res.status_code == 201
    event1_id = event1_res.json()["id"]

    tier_payload = {
        "name": "Event 1 Regular Ticket",
        "price": 20.0,
        "capacity": 10
    }
    tier_res = client.post(f"/api/events/{event1_id}/tiers", json=tier_payload)
    assert tier_res.status_code == 201
    tier_id = tier_res.json()["id"]

    # 2. Create event 2
    event2_payload = {
        "name": "Event Two",
        "description": "Valid event 2.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event2_res = client.post("/api/events", json=event2_payload)
    assert event2_res.status_code == 201
    event2_id = event2_res.json()["id"]

    # 3. Reserve ticket using event2_id but tier_id from event1
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    response = client.post(f"/api/events/{event2_id}/reserve", json=reserve_payload)
    assert response.status_code == 400
