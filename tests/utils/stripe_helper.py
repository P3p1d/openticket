import time
import hmac
import hashlib
import json

def generate_stripe_signature(payload: bytes, secret: str) -> str:
    """Generates a valid Stripe-Signature header value for webhook requests."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    mac = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={mac}"

def build_checkout_completed_event(booking_session_id: str, amount_total: int = 5000) -> dict:
    """Constructs the JSON payload structure of a Stripe checkout.session.completed event."""
    return {
        "id": "evt_test_webhook_123",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_mock_123",
                "client_reference_id": booking_session_id,
                "amount_total": amount_total,
                "currency": "usd",
                "payment_status": "paid"
            }
        }
    }
