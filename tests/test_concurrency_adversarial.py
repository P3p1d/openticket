import os
import time
import threading
import json
import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

# Set the environment variable before importing database / app components
os.environ["DATABASE_URL"] = "sqlite:///./test_openticket.db"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_mock_secret"

import uvicorn
from src.backend.main import app
from src.backend.database import engine, SessionLocal
from src.backend.models import Base, BookingSession, Ticket, TicketTier
from sqlalchemy import select
from tests.utils.stripe_helper import generate_stripe_signature, build_checkout_completed_event

@pytest.fixture(scope="module")
def server():
    # Clean any old test database
    test_db = "./test_openticket.db"
    for suffix in ["", "-wal", "-shm"]:
        path = f"{test_db}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    # Ensure tables are created in the test database
    Base.metadata.create_all(bind=engine)
    
    # Start uvicorn server in a background thread
    config = uvicorn.Config(app, host="127.0.0.1", port=8013, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    
    # Wait for server to start up by polling the root endpoint
    url = "http://127.0.0.1:8013"
    for _ in range(50):
        try:
            response = httpx.get(url)
            if response.status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(0.1)
            
    yield url
    
    # Shutdown server
    server.should_exit = True
    thread.join(timeout=5)
    
    # Clean up database connections and file
    engine.dispose()
    for suffix in ["", "-wal", "-shm"]:
        path = f"{test_db}{suffix}"
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

def test_oversell_via_expired_reservation(server):
    client = httpx.Client(base_url=server)
    
    # 1. Create an event
    event_data = {
        "name": "Adversarial Event",
        "description": "Overselling test",
        "date": "2026-06-25T20:00:00",
        "location": "Virtual"
    }
    res = client.post("/api/events", json=event_data)
    assert res.status_code == 201
    event = res.json()
    event_id = event["id"]
    
    # 2. Create a ticket tier with capacity = 5
    tier_data = {
        "name": "GA VIP",
        "price": 100.0,
        "capacity": 5
    }
    res = client.post(f"/api/events/{event_id}/tiers", json=tier_data)
    assert res.status_code == 201
    tier = res.json()
    tier_id = tier["id"]
    
    # 3. User A reserves 5 tickets (entire capacity)
    res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 5}
    )
    assert res.status_code == 201
    user_a_session = res.json()
    user_a_booking_id = user_a_session["id"]
    
    # Verify that capacity is now fully booked
    res_full = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    assert res_full.status_code == 400
    assert "capacity" in res_full.json()["detail"].lower()
    
    # 4. Simulate expiration of User A's session by directly updating the database
    db = SessionLocal()
    try:
        booking = db.get(BookingSession, user_a_booking_id)
        assert booking is not None
        # Move the expiration date to the past
        booking.expires_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()
        
    # 5. User B reserves 5 tickets (they should be allowed now since User A's reservation is expired)
    res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 5}
    )
    assert res.status_code == 201
    user_b_session = res.json()
    user_b_booking_id = user_b_session["id"]
    
    # 6. Now both users complete payment via Stripe Webhook
    secret = "whsec_mock_secret"
    
    # Webhook for User A (who had expired reservation)
    webhook_payload_a = build_checkout_completed_event(user_a_booking_id, amount_total=50000)
    webhook_payload_a["data"]["object"]["payment_intent"] = "pi_test_mock_123"
    payload_bytes_a = json.dumps(webhook_payload_a).encode('utf-8')
    sig_a = generate_stripe_signature(payload_bytes_a, secret)
    res_webhook_a = client.post("/api/webhooks/stripe", content=payload_bytes_a, headers={"Stripe-Signature": sig_a})
    assert res_webhook_a.status_code == 200
    
    # Webhook for User B (the active reservation)
    webhook_payload_b = build_checkout_completed_event(user_b_booking_id, amount_total=50000)
    payload_bytes_b = json.dumps(webhook_payload_b).encode('utf-8')
    sig_b = generate_stripe_signature(payload_bytes_b, secret)
    res_webhook_b = client.post("/api/webhooks/stripe", content=payload_bytes_b, headers={"Stripe-Signature": sig_b})
    assert res_webhook_b.status_code == 200
    
    # 7. Check the database for total tickets sold and valid
    db = SessionLocal()
    try:
        booking_a = db.get(BookingSession, user_a_booking_id)
        booking_b = db.get(BookingSession, user_b_booking_id)
        
        print(f"\n--- Vulnerability Check Results ---")
        print(f"User A (Expired) Booking Status: {booking_a.status}")
        print(f"User B (Active) Booking Status: {booking_b.status}")
        
        valid_tickets = db.execute(
            select(Ticket).where(Ticket.tier_id == tier_id, Ticket.status == "valid")
        ).scalars().all()
        
        print(f"Total valid tickets in DB: {len(valid_tickets)} (Capacity: 5)")
        
        # User A's booking status in the DB should be "failed" (or "expired")
        assert booking_a.status in ("failed", "expired")
        
        # User A's tickets should NOT be marked as "valid"
        tickets_a_stmt = select(Ticket).where(Ticket.booking_session_id == user_a_booking_id)
        tickets_a = db.execute(tickets_a_stmt).scalars().all()
        for ticket in tickets_a:
            assert ticket.status != "valid"
            
        # User B's booking status in DB should be "paid", and its tickets should be "valid"
        assert booking_b.status == "paid"
        tickets_b_stmt = select(Ticket).where(Ticket.booking_session_id == user_b_booking_id)
        tickets_b = db.execute(tickets_b_stmt).scalars().all()
        assert len(tickets_b) == 5
        for ticket in tickets_b:
            assert ticket.status == "valid"
            
        # The total number of valid tickets in the database for the tier must be exactly 5
        assert len(valid_tickets) == 5
        
    finally:
        db.close()

def test_concurrent_reservations_high_concurrency(server):
    client = httpx.Client(base_url=server)
    
    # 1. Create an event
    event_data = {
        "name": "High Concurrency Event",
        "description": "Stress testing",
        "date": "2026-06-25T20:00:00",
        "location": "Main Stage"
    }
    res = client.post("/api/events", json=event_data)
    assert res.status_code == 201
    event = res.json()
    event_id = event["id"]
    
    # 2. Create a ticket tier with capacity = 10
    tier_data = {
        "name": "GA Regular",
        "price": 40.0,
        "capacity": 10
    }
    res = client.post(f"/api/events/{event_id}/tiers", json=tier_data)
    assert res.status_code == 201
    tier = res.json()
    tier_id = tier["id"]
    
    # 3. Spawn 40 concurrent requests to reserve 1, 2 or 3 tickets
    # Total requests = 40, different threads requesting varying quantities
    # Max capacity = 10.
    quantities = [1, 2, 3, 1] * 10  # 40 requests total, sum is 70
    
    def make_reservation(quantity):
        with httpx.Client(base_url=server) as thread_client:
            try:
                response = thread_client.post(
                    f"/api/events/{event_id}/reserve",
                    json={"tier_id": tier_id, "quantity": quantity},
                    timeout=15.0
                )
                return response.status_code, response.json(), quantity
            except Exception as e:
                return 500, {"error": str(e)}, quantity
                
    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(make_reservation, q) for q in quantities]
        results = [f.result() for f in futures]
        
    # Process results
    successes = [r for r in results if r[0] == 201]
    failures = [r for r in results if r[0] == 400]
    errors = [r for r in results if r[0] not in (201, 400)]
    
    print(f"\n--- High Concurrency Results ---")
    print(f"Successes: {len(successes)}")
    print(f"Failures: {len(failures)}")
    print(f"Errors: {len(errors)}")
    
    total_reserved = sum(r[1]["quantity"] for r in successes)
    print(f"Total Reserved Quantity: {total_reserved} (Capacity: 10)")
    
    # Assertions
    assert total_reserved <= 10, f"Capacity exceeded! Total reserved: {total_reserved}"
    assert len(errors) == 0, f"Expected 0 errors, got {len(errors)}: {errors}"
    
    # Verify DB state
    db = SessionLocal()
    try:
        tickets = db.execute(
            select(Ticket).where(Ticket.tier_id == tier_id)
        ).scalars().all()
        assert len(tickets) == total_reserved, f"Tickets count in DB ({len(tickets)}) doesn't match total reserved ({total_reserved})"
    finally:
        db.close()
