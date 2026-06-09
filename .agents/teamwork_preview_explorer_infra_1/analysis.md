# OpenTicket E2E Test Infrastructure Recommendations

This report presents recommendations for the End-to-End (E2E) test infrastructure design for OpenTicket, an open-source, self-hosted ticket selling web application in Python. The recommendations are based on an analysis of the user requirements in `ORIGINAL_REQUEST.md` and the orchestrator files in `.agents/orchestrator/PROJECT.md` and `.agents/sub_orch_e2e/`.

---

## Executive Summary
OpenTicket requires a robust, requirement-driven, opaque-box E2E test suite supporting SQLite and PostgreSQL databases, verifying high-concurrency booking safety, and simulating offline payment completion (Stripe). This design achieves those goals using a `pytest` framework with `httpx` async clients, a background `live_server` subprocess fixture for testing true DB-level concurrency, and a cryptographic signing engine helper to simulate Stripe Webhook validation completely offline.

---

## Recommendations & Design Analysis

### 1. Test Framework and Environment Setup

* **Core Test Runner**: `pytest` is recommended for standard python test runner integration.
* **HTTP Client**: `httpx` is recommended because of its asynchronous capabilities, connection pooling, and robustness under concurrency tests, surpassing FastAPI's synchronous `TestClient` for concurrent request flows.
* **Environment Configuration**: Set up a `.env.test` file or populate variables in `conftest.py`:
  * `DATABASE_URL`: Set to a dedicated test DB (e.g., `sqlite:///./test_openticket.db`).
  * `STRIPE_API_KEY`: Dummy test key (e.g., `sk_test_mockkey`).
  * `STRIPE_WEBHOOK_SECRET`: Static webhook verification secret (e.g., `whsec_testsecret`).
* **Test Database Isolation & SQLite WAL Mode**:
  * Set up session-scoped schema initialization.
  * To test concurrency correctly on SQLite, the test database engine must be configured to run in **Write-Ahead Logging (WAL)** mode: `PRAGMA journal_mode=WAL;`. This allows concurrent readers and non-blocking writers, preventing SQLite "database is locked" errors during rapid concurrent requests.
* **Live Server Fixture**:
  * FastAPI `TestClient` operates in-process and is synchronous, meaning concurrent HTTP requests are blocked or serialized.
  * To verify row-level locks (e.g., `SELECT FOR UPDATE`), the E2E tests should run the FastAPI app as a background process or thread using `uvicorn`, allowing `httpx.AsyncClient` from the test runner to dispatch concurrent requests.

#### Recommended `conftest.py` Design:
```python
import os
import pytest
import uvicorn
from multiprocessing import Process
import time
import socket
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.backend.database import Base, get_db
from src.backend.main import app

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="session")
def test_db():
    test_db_url = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_openticket.db")
    engine = create_engine(
        test_db_url, 
        connect_args={"check_same_thread": False} if "sqlite" in test_db_url else {}
    )
    
    if "sqlite" in test_db_url:
        with engine.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield TestingSessionLocal
    
    Base.metadata.drop_all(bind=engine)
    if "test_openticket.db" in test_db_url:
        for ext in ["", "-wal", "-shm"]:
            try:
                os.remove(f"./test_openticket.db{ext}")
            except OSError:
                pass

@pytest.fixture(scope="session")
def live_server(test_db):
    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()
            
    app.dependency_overrides[get_db] = override_get_db
    port = get_free_port()
    
    proc = Process(
        target=uvicorn.run, 
        args=(app,), 
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "critical"}
    )
    proc.start()
    time.sleep(0.5) 
    
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    
    proc.terminate()
    proc.join()
```

---

### 2. Stripe Checkout and Webhook Mocking Strategy

#### A. Mocking Checkout Redirect
Instead of directly calling external Stripe APIs, design a modular `PaymentGateway` adapter pattern inside the backend:
* **Interface**: `src/backend/payment/gateway.py` defining `create_checkout_session(...) -> str`.
* **Production**: `StripePaymentGateway` calling `stripe.checkout.Session.create(...)`.
* **Testing**: `MockPaymentGateway` generating a mock URL:
  `f"http://127.0.0.1:8000/mock-stripe-checkout?session_id=cs_test_mock_{booking_session_id}"`.
* In test setups, use FastAPI's dependency injection overrides to swap `StripePaymentGateway` with `MockPaymentGateway`.

#### B. Simulating & Verification of Webhook Events
To test the Stripe Webhook handler (`POST /api/webhooks/stripe`) offline:
* Construct a standard Stripe `checkout.session.completed` event structure:
  ```json
  {
    "id": "evt_test_123",
    "object": "event",
    "type": "checkout.session.completed",
    "data": {
      "object": {
        "id": "cs_test_mock_123",
        "metadata": {
          "booking_session_id": "booking_session_uuid_abc"
        },
        "payment_status": "paid"
      }
    }
  }
  ```
* Construct a cryptographic webhook signature in the test using `hmac` and SHA256. This matches the exact verification logic executed by `stripe.Webhook.construct_event`, allowing signature validation to pass offline:
  ```python
  import hmac
  import hashlib
  import time
  import json

  def generate_stripe_signature(payload_dict: dict, webhook_secret: str) -> str:
      timestamp = str(int(time.time()))
      payload_str = json.dumps(payload_dict)
      signed_payload = f"{timestamp}.{payload_str}".encode("utf-8")
      signature = hmac.new(
          webhook_secret.encode("utf-8"),
          signed_payload,
          hashlib.sha256
      ).hexdigest()
      return f"t={timestamp},v1={signature}"
  ```
* Send a `POST` request to `/api/webhooks/stripe` with headers:
  `{"Stripe-Signature": signature_header}` and the raw JSON payload.

---

### 3. Test Suite Organization (Tiers 1-4)

The test suite directory structure must be explicitly split into 4 tiers to support targeted validation:

* **Tier 1: Feature Coverage (>=25 cases)**: Isolation tests targeting each major requirement block.
  * *Event & Tier Mgmt*: Verify CRUD APIs.
  * *Booking Session*: Verify reservation timeouts, initial capacity holds.
  * *Stripe Integration*: Webhook lifecycle, success/cancel page updates.
  * *Monospace UI*: Verify branding HTML custom styles, layout absence of generic gradients.
  * *Widget*: Check loading vanilla script and widget config retrieval.
* **Tier 2: Boundary & Corner Cases (>=25 cases)**: Edge case conditions.
  * *Reservation Timeout*: Releasing tickets when checkout is not completed within limit.
  * *Concurrency locks*: Concurrency testing.
  * *Validation bounds*: Verify bounds (negative price, capacity, negative tickets, etc.).
  * *Security*: SQL Injection verification and invalid Webhook signatures validation.
* **Tier 3: Cross-Feature Integration (>=5 cases)**: Interlocking subsystems.
  * *Branding & Widget*: Changing branding settings in admin updates the embeddable script configuration.
  * *Timeout & Re-reservation*: Booking fails on capacity -> timeout -> booking succeeds.
* **Tier 4: Real-world Application Scenarios (>=5 cases)**: Full integration.
  * *High-volume presale*: Concurrent user load simulation.
  * *Multitenant isolation*: Simultaneous bookings on independent events.

See detailed directory structure layout in `proposed_TEST_INFRA.md`.

---

### 4. Proposed `TEST_INFRA.md` Location
The drafted contents of `TEST_INFRA.md` have been generated as:
`c:\Development\openticket\.agents\teamwork_preview_explorer_infra_1\proposed_TEST_INFRA.md`

This file is fully formatted and ready to be placed at the project root (`c:\Development\openticket\TEST_INFRA.md`) during the next implementation phase.
