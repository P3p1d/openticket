import pytest
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    c = TestClient(app)
    c.cookies.set("session_token", "admin_session")
    return c

def test_create_event_api_success(client):
    payload = {
        "name": "Underground Techno Night",
        "description": "An intense night of underground techno beats.",
        "date": "2026-06-15T22:00:00",
        "location": "The Industrial Warehouse"
    }
    response = client.post("/api/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert "id" in data

def test_list_events_api_success(client):
    payload = {
        "name": "Event List Test",
        "description": "Listing test event.",
        "date": "2026-06-16T20:00:00",
        "location": "Vaporwave Lounge"
    }
    client.post("/api/events", json=payload)
    
    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(e["name"] == "Event List Test" for e in data)

def test_retrieve_event_by_id_api_success(client):
    payload = {
        "name": "Single Event Retrieve Test",
        "description": "Testing retrieval by ID.",
        "date": "2026-06-17T21:00:00",
        "location": "Industrial Vault"
    }
    create_res = client.post("/api/events", json=payload)
    event_id = create_res.json()["id"]
    
    response = client.get(f"/api/events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == event_id
    assert data["name"] == payload["name"]

def test_create_event_empty_name_fails(client):
    payload = {
        "name": "",
        "description": "Empty name event should fail validation.",
        "date": "2026-06-18T19:00:00",
        "location": "Virtual Reality Dome"
    }
    response = client.post("/api/events", json=payload)
    assert response.status_code == 422

def test_get_event_by_invalid_id_404(client):
    response = client.get("/api/events/999999")
    assert response.status_code == 404

def test_admin_dashboard_html_rendering(client):
    payload = {
        "name": "Dashboard Render Event",
        "description": "For testing HTML rendering.",
        "date": "2026-06-19T22:00:00",
        "location": "Cyberpunk Club"
    }
    client.post("/api/events", json=payload)
    
    response = client.get("/admin/events")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert "OpenTicket Admin" in html_content
    assert "Dashboard Render Event" in html_content

def test_admin_create_event_form_html(client):
    response = client.get("/admin/events/new")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html_content = response.text
    assert 'name="name"' in html_content
    assert 'name="description"' in html_content
    assert 'name="date"' in html_content
    assert 'name="location"' in html_content
