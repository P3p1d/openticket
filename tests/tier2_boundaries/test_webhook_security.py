import json
import time
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from tests.utils.stripe_helper import generate_stripe_signature, build_checkout_completed_event

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def booking_session_id(client):
    from datetime import datetime, timedelta, timezone
    event_payload = {
        "name": "Stripe Webhook Event",
        "description": "For testing Stripe webhook.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Warehouse Studio B"
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

def test_stripe_webhook_missing_signature_fails(client, booking_session_id):
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    response = client.post("/api/webhooks/stripe", content=payload_bytes)
    assert response.status_code == 400
    assert "missing stripe-signature" in response.json()["detail"].lower()

def test_stripe_webhook_invalid_signature_format_fails(client, booking_session_id):
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    headers = {"Stripe-Signature": "invalid_format_signature_no_t_equals"}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 400

def test_stripe_webhook_expired_signature_fails(client, booking_session_id):
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    # Generate an expired signature (10 minutes ago, Stripe default is 5 mins tolerance)
    timestamp = str(int(time.time()) - 600)
    signed_payload = f"{timestamp}.{payload_bytes.decode('utf-8')}"
    secret = "whsec_mock_secret"
    mac = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    expired_signature = f"t={timestamp},v1={mac}"
    
    headers = {"Stripe-Signature": expired_signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 400

def test_stripe_webhook_incorrect_secret_fails(client, booking_session_id):
    webhook_payload = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(webhook_payload).encode('utf-8')
    
    # Generate signature using incorrect secret
    signature = generate_stripe_signature(payload_bytes, "incorrect_secret_val")
    
    headers = {"Stripe-Signature": signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 400

def test_stripe_webhook_empty_payload_fails(client):
    payload_bytes = b""
    
    # Generate signature for empty payload
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}."
    secret = "whsec_mock_secret"
    mac = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    signature = f"t={timestamp},v1={mac}"
    
    headers = {"Stripe-Signature": signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 400

def test_stripe_webhook_non_checkout_event_ignored(client):
    non_checkout_payload = {
        "id": "evt_test_ignored_123",
        "object": "event",
        "type": "payment_intent.created",
        "data": {
            "object": {
                "id": "pi_12345",
                "amount": 5000
            }
        }
    }
    payload_bytes = json.dumps(non_checkout_payload).encode('utf-8')
    signature = generate_stripe_signature(payload_bytes, "whsec_mock_secret")
    
    headers = {"Stripe-Signature": signature}
    response = client.post("/api/webhooks/stripe", content=payload_bytes, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
