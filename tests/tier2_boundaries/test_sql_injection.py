import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_sql_injection_event_id_fails(client):
    # 1. Create a valid event first to ensure table has data
    event_payload = {
        "name": "SQL Injection Event",
        "description": "To test injection safety.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    create_res = client.post("/api/events", json=event_payload)
    assert create_res.status_code == 201

    # 2. Attempt SQL injection in the event_id path parameter
    injection_path = "/api/events/1; DROP TABLE events; --"
    response = client.get(injection_path)
    
    # Path parameter validation in FastAPI dictates that event_id must be int.
    # Therefore, this should fail with 422 Unprocessable Entity.
    assert response.status_code == 422

    # 3. Verify that the events table was NOT dropped and we can still list events
    list_res = client.get("/api/events")
    assert list_res.status_code == 200
    events = list_res.json()
    assert len(events) >= 1
    assert any(e["name"] == "SQL Injection Event" for e in events)

def test_sql_injection_tier_name_escaped(client):
    # 1. Create a valid event
    event_payload = {
        "name": "Event for Tier Escape Test",
        "description": "To test injection safety.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Test Venue"
    }
    event_res = client.post("/api/events", json=event_payload)
    assert event_res.status_code == 201
    event_id = event_res.json()["id"]

    # 2. Create tier with an SQL injection payload in name
    injection_name = "Standard'; DROP TABLE events; --"
    tier_payload = {
        "name": injection_name,
        "price": 25.0,
        "capacity": 50
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    assert tier_res.status_code == 201
    
    # 3. Retrieve event tiers and verify name is stored and escaped correctly (as data, not executable code)
    get_tiers_res = client.get(f"/api/events/{event_id}/tiers")
    assert get_tiers_res.status_code == 200
    tiers = get_tiers_res.json()
    assert len(tiers) >= 1
    assert tiers[0]["name"] == injection_name

    # 4. Verify that the events table was NOT dropped and listing events still works
    list_res = client.get("/api/events")
    assert list_res.status_code == 200
