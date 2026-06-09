import json
import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.models import BookingSession, Ticket
from tests.utils.stripe_helper import generate_stripe_signature, build_checkout_completed_event

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def booking_session_id(client):
    # 1. Create event
    event_payload = {
        "name": "Stripe Integration Event",
        "description": "For testing Stripe checkout and webhook.",
        "date": "2026-06-22T21:00:00",
        "location": "Warehouse Studio A"
    }
    event_res = client.post("/api/events", json=event_payload).json()
    event_id = event_res["id"]
    
    # 2. Create tier
    tier_payload = {
        "name": "Standard Stripe Ticket",
        "price": 40.0,
        "capacity": 10
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload).json()
    tier_id = tier_res["id"]
    
    # 3. Reserve
    reserve_payload = {
        "tier_id": tier_id,
        "quantity": 1
    }
    booking_res = client.post(f"/api/events/{event_id}/reserve", json=reserve_payload).json()
    return booking_res["id"]

def test_create_checkout_session_success(client, booking_session_id):
    response = client.post(f"/api/bookings/{booking_session_id}/checkout")
    assert response.status_code == 200
    data = response.json()
    assert "checkout_url" in data or "url" in data
    url = data.get("checkout_url") or data.get("url")
    assert "stripe.com" in url

def test_create_checkout_session_invalid_booking_fails(client):
    response = client.post("/api/bookings/invalid-booking-session-id-1234/checkout")
    assert response.status_code == 404

def test_stripe_webhook_completed_success(client, booking_session_id, db_session):
    # Create checkout completed event
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    # Generate signature using the mock secret
    secret = "whsec_mock_secret"
    signature = generate_stripe_signature(payload_bytes, secret)
    
    # Dispatch webhook
    headers = {"Stripe-Signature": signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Refresh database session to verify changes
    db_session.expire_all()
    booking = db_session.get(BookingSession, booking_session_id)
    assert booking is not None
    assert booking.status == "paid"
    
    tickets = db_session.query(Ticket).filter_by(booking_session_id=booking_session_id).all()
    assert len(tickets) == 1
    for ticket in tickets:
        assert ticket.status == "valid"
        assert ticket.ticket_code is not None

def test_stripe_webhook_completed_invalid_booking_fails(client):
    # Build webhook event with invalid booking id
    webhook_payload = build_checkout_completed_event("non-existent-booking-id")
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    secret = "whsec_mock_secret"
    signature = generate_stripe_signature(payload_bytes, secret)
    
    headers = {"Stripe-Signature": signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code in (404, 400)

def test_stripe_webhook_completed_signature_verification(client, booking_session_id):
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    # Invalid signature test (uses incorrect secret)
    bad_signature = generate_stripe_signature(payload_bytes, "wrong_secret")
    
    headers = {"Stripe-Signature": bad_signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 400
