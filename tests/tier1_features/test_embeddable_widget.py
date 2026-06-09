import pytest
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_widget_js_served(client):
    response = client.get("/static/widget.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert "OpenTicket Monospace Widget" in response.text

def test_widget_config_endpoint(client):
    response = client.get("/api/widget/config")
    assert response.status_code == 200
    data = response.json()
    assert "site_name" in data
    assert "site_logo" in data
    assert "primary_color" in data
    assert "accent_color" in data

def test_widget_cors_headers(client):
    # Retrieve configuration endpoint with Origin header
    headers = {"Origin": "https://external-site.com"}
    response = client.get("/api/widget/config", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] in ("*", "https://external-site.com")
    
    # Also verify OPTIONS preflight request for CORS config
    preflight_headers = {
        "Origin": "https://external-site.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type"
    }
    options_res = client.options("/api/widget/config", headers=preflight_headers)
    assert options_res.status_code in (200, 204)
    assert "access-control-allow-origin" in options_res.headers
    assert "access-control-allow-methods" in options_res.headers
