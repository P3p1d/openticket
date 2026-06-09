import pytest
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def event_id(client):
    payload = {
        "name": "Tier Management Event",
        "description": "For testing ticket tiers.",
        "date": "2026-06-20T20:00:00",
        "location": "Dark Ambient Crypt"
    }
    response = client.post("/api/events", json=payload)
    return response.json()["id"]

def test_create_tier_success(client, event_id):
    payload = {
        "name": "General Admission",
        "price": 25.0,
        "capacity": 100
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["price"] == payload["price"]
    assert data["capacity"] == payload["capacity"]
    assert "id" in data

def test_list_tiers_success(client, event_id):
    # Create a couple of tiers
    t1 = {"name": "VIP Tier", "price": 100.0, "capacity": 20}
    t2 = {"name": "Early Bird", "price": 15.0, "capacity": 50}
    client.post(f"/api/events/{event_id}/tiers", json=t1)
    client.post(f"/api/events/{event_id}/tiers", json=t2)
    
    # Check event retrieval which returns list of tiers
    response = client.get(f"/api/events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    tiers = data["tiers"]
    assert len(tiers) >= 2
    assert any(t["name"] == "VIP Tier" for t in tiers)
    assert any(t["name"] == "Early Bird" for t in tiers)

def test_create_tier_zero_price_success(client, event_id):
    payload = {
        "name": "Free Ticket Tier",
        "price": 0.0,
        "capacity": 50
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=payload)
    assert response.status_code == 201
    assert response.json()["price"] == 0.0

def test_create_tier_empty_name_fails(client, event_id):
    payload = {
        "name": "",
        "price": 20.0,
        "capacity": 100
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=payload)
    assert response.status_code == 422

def test_create_tier_negative_capacity_fails(client, event_id):
    payload = {
        "name": "Invalid Capacity Tier",
        "price": 20.0,
        "capacity": -10
    }
    response = client.post(f"/api/events/{event_id}/tiers", json=payload)
    assert response.status_code == 422

def test_get_tiers_endpoint_success(client, event_id):
    t1 = {"name": "VIP Tier 2", "price": 120.0, "capacity": 25}
    t2 = {"name": "Early Bird 2", "price": 18.0, "capacity": 55}
    client.post(f"/api/events/{event_id}/tiers", json=t1)
    client.post(f"/api/events/{event_id}/tiers", json=t2)
    
    response = client.get(f"/api/events/{event_id}/tiers")
    assert response.status_code == 200
    tiers = response.json()
    assert len(tiers) >= 2
    assert any(t["name"] == "VIP Tier 2" for t in tiers)
    assert any(t["name"] == "Early Bird 2" for t in tiers)

def test_get_tiers_endpoint_nonexistent_event_fails(client):
    response = client.get("/api/events/99999/tiers")
    assert response.status_code == 404
