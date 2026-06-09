import os
import time
import threading
import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor

# Set the environment variable before importing database / app components
os.environ["DATABASE_URL"] = "sqlite:///./test_openticket.db"

import uvicorn
from src.backend.main import app
from src.backend.database import engine, SessionLocal
from src.backend.models import Base, BookingSession, Ticket
from sqlalchemy import select

@pytest.fixture(scope="module")
def server():
    # Clean any old test database
    test_db = "./test_openticket.db"
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass

    # Ensure tables are created in the test database
    Base.metadata.create_all(bind=engine)
    
    # Start uvicorn server in a background thread
    config = uvicorn.Config(app, host="127.0.0.1", port=8012, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    
    # Wait for server to start up by polling the root endpoint
    url = "http://127.0.0.1:8012"
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
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass

def test_concurrent_reservations(server):
    client = httpx.Client(base_url=server)
    
    # 1. Create an event
    event_data = {
        "name": "Concert",
        "description": "Live Music",
        "date": "2026-06-15T20:00:00",
        "location": "Main Stage"
    }
    res = client.post("/api/events", json=event_data)
    assert res.status_code == 201
    event = res.json()
    event_id = event["id"]
    
    # 2. Create a ticket tier with capacity = 5
    tier_data = {
        "name": "GA",
        "price": 50.0,
        "capacity": 5
    }
    res = client.post(f"/api/events/{event_id}/tiers", json=tier_data)
    assert res.status_code == 201
    tier = res.json()
    tier_id = tier["id"]
    
    # 3. Spawn 12 concurrent requests to reserve 1 ticket each
    num_requests = 12
    quantity = 1
    
    def make_reservation():
        with httpx.Client(base_url=server) as thread_client:
            try:
                response = thread_client.post(
                    f"/api/events/{event_id}/reserve",
                    json={"tier_id": tier_id, "quantity": quantity},
                    timeout=15.0
                )
                return response.status_code, response.json()
            except Exception as e:
                return 500, {"error": str(e)}
                
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(make_reservation) for _ in range(num_requests)]
        results = [f.result() for f in futures]
        
    # 4. Process results
    successes = [r for r in results if r[0] == 201]
    failures = [r for r in results if r[0] == 400]
    errors = [r for r in results if r[0] not in (201, 400)]
    
    print(f"\n--- Reservation Results (Total: {num_requests}) ---")
    print(f"Successes (201): {len(successes)}")
    print(f"Failures (400): {len(failures)}")
    print(f"Other Errors: {len(errors)}")
    for i, r in enumerate(results):
        print(f"Request {i+1}: Status {r[0]} - Response: {r[1]}")
        
    # Assertions
    assert len(successes) == 5, f"Expected 5 successful reservations, got {len(successes)}"
    assert len(failures) == 7, f"Expected 7 failures, got {len(failures)}"
    assert len(errors) == 0, f"Expected 0 unexpected errors, got {len(errors)}: {errors}"
    
    # 5. Verify database state matches expected reservation count
    db = SessionLocal()
    try:
        # Check active booking sessions
        sessions_stmt = select(BookingSession).where(BookingSession.tier_id == tier_id)
        sessions = db.execute(sessions_stmt).scalars().all()
        assert len(sessions) == 5, f"Expected 5 booking sessions in DB, got {len(sessions)}"
        for session in sessions:
            assert session.status == "reserved"
            assert len(session.tickets) == 1
            
        # Check total tickets in DB
        tickets_stmt = select(Ticket).where(Ticket.tier_id == tier_id)
        tickets = db.execute(tickets_stmt).scalars().all()
        assert len(tickets) == 5, f"Expected 5 tickets in DB, got {len(tickets)}"
    finally:
        db.close()
