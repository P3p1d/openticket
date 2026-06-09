import pytest
from fastapi.testclient import TestClient
from src.backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_admin_branding_get_post(client):
    # Test GET branding page
    response = client.get("/admin/branding")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Branding Customization" in response.text
    
    # Test POST branding customization form submission
    payload = {
        "site_name": "Industrial Tix",
        "site_logo": "http://logo.url/logo.png",
        "primary_color": "#0d0d0d",
        "accent_color": "#00ffcc"
    }
    post_res = client.post("/admin/branding", data=payload)
    assert post_res.status_code == 200
    assert "text/html" in post_res.headers["content-type"]
    
    # Check that new settings are saved and rendered in the response
    html = post_res.text
    assert "Industrial Tix" in html
    assert "http://logo.url/logo.png" in html
    assert "#0d0d0d" in html
    assert "#00ffcc" in html

def test_monospace_styles_in_html(client):
    # Check that HTML views (like admin dashboard) contains monospace font styles or classes
    response = client.get("/admin/events")
    assert response.status_code == 200
    html = response.text
    assert "font-family: monospace" in html or "font-family: monospace, Courier" in html
    # Check for dark theme background styling
    assert "background-color: var(--bg-color)" in html or "background-color: #121212" in html

def test_branding_customization_rendered_in_html(client):
    # Apply new branding
    branding_payload = {
        "site_name": "Cyber Rave Tickets",
        "site_logo": "https://cyber.rave/logo.svg",
        "primary_color": "#010101",
        "accent_color": "#ff0055"
    }
    client.post("/admin/branding", data=branding_payload)
    
    # Retrieve the dashboard page and check if custom branding is rendered
    response = client.get("/admin/events")
    assert response.status_code == 200
    html = response.text
    assert "Cyber Rave Tickets" in html
    assert "https://cyber.rave/logo.svg" in html
    assert "--primary-color: #010101" in html
    assert "--accent-color: #ff0055" in html
