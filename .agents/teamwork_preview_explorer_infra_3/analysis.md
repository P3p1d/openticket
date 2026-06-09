# E2E Test Infrastructure Design - OpenTicket

This document outlines the proposed E2E testing infrastructure for OpenTicket, resolving the framework configurations, payment gateway mocking, test suite structure (Tiers 1-4), and the draft content for `TEST_INFRA.md`.

---

## 1. Test Framework and Environment Setup

### 1.1 Core Tools & Libraries
- **pytest**: The primary test runner and framework.
- **httpx**: Used for sending synchronous and asynchronous HTTP requests to the FastAPI application (replacing or wrapping `fastapi.testclient.TestClient`). Using `httpx.AsyncClient` is critical for concurrency tests.
- **pytest-asyncio**: Provides support for writing asynchronous test cases (`async def test_*`) and handling async fixtures.
- **sqlalchemy**: Necessary to run test database setup, verify state inside the database, and test row-level concurrency behaviors.

### 1.2 Pytest Configuration (`pytest.ini`)
The configuration will reside in `tests/pytest.ini` (or the project root) to maintain consistent test execution settings:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning
```

### 1.3 Test Environment & Configuration Setup
To prevent tests from mutating local database state or hitting real external services, we define a dedicated test environment.
- Settings are loaded via `pydantic-settings` from environment variables.
- We will use a dedicated SQLite file `test_openticket.db` for testing. In-memory SQLite (`sqlite:///:memory:`) is avoided because concurrent test requests running in separate database sessions/threads cannot share a single standard in-memory connection easily.
- A FastAPI dependency override fixture is used in `conftest.py` to inject these configurations:

```python
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing anything else
os.environ["DATABASE_URL"] = "sqlite:///./test_openticket.db"
os.environ["STRIPE_API_KEY"] = "sk_test_mock"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_mock_secret"
os.environ["TESTING"] = "True"

from src.backend.main import app
from src.backend.database import Base, get_db
from src.backend.config import get_settings, Settings

# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_openticket.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def override_settings():
    return Settings(
        DATABASE_URL=TEST_DATABASE_URL,
        STRIPE_API_KEY="sk_test_mock",
        STRIPE_WEBHOOK_SECRET="whsec_mock_secret",
        TESTING=True
    )

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables to guarantee test isolation
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_openticket.db"):
        try:
            os.remove("./test_openticket.db")
        except PermissionError:
            pass

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_settings
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

---

## 2. Stripe Checkout Mocking and Webhook Simulation

### 2.1 Mocking Stripe Checkout Session Redirect
When `POST /api/bookings/{booking_session_id}/checkout` is called, the application requests a checkout session from Stripe. We intercept this request via a `monkeypatch` fixture in `conftest.py` targeting the `stripe.checkout.Session.create` API call.

```python
@pytest.fixture
def mock_stripe_checkout(monkeypatch):
    class MockSession:
        id = "cs_test_mock_123"
        url = "https://checkout.stripe.com/c/pay/cs_test_mock_123"

    def mock_create(*args, **kwargs):
        # We can extract metadata or success/cancel URLs here to test logic if needed
        return MockSession()

    monkeypatch.setattr("stripe.checkout.Session.create", mock_create)
```

This setup provides an opaque-box verification: the endpoint continues to execute its internal mapping and logic, returning the mock URL (`https://checkout.stripe.com/c/pay/cs_test_mock_123`) to the client without calling external Stripe services.

### 2.2 Simulating/Posting Stripe Webhook Events
To test the webhook validation endpoint (`POST /api/webhooks/stripe`) under true E2E conditions without disabling signature checks, the test suite will dynamically generate valid Stripe signatures using the test webhook secret.

#### Signature Construction Utility (`tests/utils/stripe_helper.py`):
```python
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
```

#### Test Execution Example:
```python
def test_stripe_webhook_processing(client, setup_db):
    # Setup test event and reservation session in DB
    booking_session_id = "test-session-uuid"
    
    # Construct event payload and generate valid signature
    payload_dict = build_checkout_completed_event(booking_session_id)
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    signature = generate_stripe_signature(payload_bytes, "whsec_mock_secret")
    
    # Send mock webhook event
    response = client.post(
        "/api/webhooks/stripe",
        content=payload_bytes,
        headers={
            "Stripe-Signature": signature,
            "Content-Type": "application/json"
        }
    )
    
    assert response.status_code == 200
    # Verify booking status in database has changed to paid and ticket check-in codes were created
```

---

## 3. Test Suite Organization (Tiers 1-4)

The test suite will be organized hierarchically under `tests/` to facilitate isolated execution of testing tiers. A total of at least 60 test cases must be implemented across these folders.

```
tests/
├── conftest.py                # Global fixtures (DB connection, FastAPI client, Stripe overrides)
├── pytest.ini                 # Pytest configuration settings
├── utils/
│   ├── stripe_helper.py       # Stripe signature signature generators & webhook factory
│   └── db_helper.py           # DB seed helpers
├── tier1_features/            # Happy path isolated feature coverage (>= 25 tests)
│   ├── test_events.py         # Event CRUD operations
│   ├── test_tiers.py          # Ticket tier configurations (name, price, capacity)
│   ├── test_reservations.py   # Reservation session creation (/reserve)
│   ├── test_checkout.py       # Checkout URL retrieval (/checkout)
│   └── test_webhooks.py       # Stripe webhook payment confirmations
├── tier2_boundaries/          # Boundary & Corner cases (>= 25 tests)
│   ├── test_validation.py     # Negative prices, zero values, long strings
│   ├── test_limits.py         # Reservation attempts exceeding tier capacities (Limit, Limit+1)
│   ├── test_timeouts.py       # Expired reservation cleanup & checkout block
│   └── test_signatures.py     # Malformed stripe signatures, invalid signatures, fake events
├── tier3_integration/         # Cross-feature flows & environment configurations (>= 5 tests)
│   ├── test_customer_flow.py  # Comprehensive flow (Admin setup -> User Reserve -> Checkout -> Stripe Webhook -> Confirm)
│   ├── test_branding.py       # Branding configuration & verification of JS Widget endpoint outputs
│   └── test_db_compatibility.py # SQLite vs. PostgreSQL schema & migrations check
└── tier4_scenarios/           # Real-world loads & resilience (>= 5 tests)
    ├── test_concurrency.py    # Multi-threaded/async bookings for hot inventory (oversell prevention)
    ├── test_idempotency.py    # Duplicate Stripe webhook delivery resilience
    └── test_db_locks.py       # DB deadlocks and connection pooling lock recoveries
```

---

## 4. Draft Content for `TEST_INFRA.md`

Below is the complete, production-ready markdown content for `c:\Development\openticket\TEST_INFRA.md`.

```markdown
# OpenTicket E2E Test Infrastructure Guide

This document describes the design, execution, and structure of the requirement-driven E2E test suite for OpenTicket.

## 1. Test Architecture Overview
The OpenTicket test suite validates system requirements under opaque-box testing conditions. 
- API endpoints are tested using FastAPI's routing via `httpx` clients.
- The UI forms and Jinja2 admin templates are inspected directly by analyzing HTML response payloads.
- Stripe payment integrations are simulated and verified without hitting external servers.
- High-concurrency race condition protections (row-level database locking) are verified using multi-threaded execution.

---

## 2. Environment Setup & Configuration

### 2.1 Dependencies
Ensure testing packages are installed:
```bash
pip install -r requirements.txt
```
Key packages include:
- `pytest`: Test harness.
- `httpx`: Synchronous/Asynchronous HTTP requests.
- `pytest-asyncio`: Async test capabilities.

### 2.2 Environment Variables
The test environment overrides standard configurations. Key configuration parameters:
- `DATABASE_URL`: Defaults to `sqlite:///./test_openticket.db` for isolation.
- `STRIPE_API_KEY`: Defaults to `sk_test_mock`.
- `STRIPE_WEBHOOK_SECRET`: Defaults to `whsec_mock_secret`.
- `TESTING`: Must be set to `True` during execution.

---

## 3. Test Organization (Tiers 1-4)

The test suite is structured as follows:

1. **Tier 1 (Feature Coverage)** (`tests/tier1_features/`): Covers standard operations (Event creation, tier additions, booking, checking out, and webhook processing) in isolation.
2. **Tier 2 (Boundary & Corner Cases)** (`tests/tier2_boundaries/`): Validates handling of negative input values, capacity edge limits (e.g., reserving last ticket, and limit+1 failures), reservation expiration timeouts, and invalid signatures.
3. **Tier 3 (Integration & Cross-Feature)** (`tests/tier3_integration/`): Tests full user purchase flows, branding customization propagation, and SQLite/Postgres compatibility.
4. **Tier 4 (Real-world Scenarios)** (`tests/tier4_scenarios/`): Tests high-concurrency oversell prevention, duplicate webhook payments (idempotency checks), and DB lock timeouts.

---

## 4. Running the Tests

To run the full E2E test suite:
```bash
pytest -v
```

To run a specific test tier (e.g., Tier 4 Real-world Scenarios):
```bash
pytest -v tests/tier4_scenarios/
```

To run a single file:
```bash
pytest -v tests/tier4_scenarios/test_concurrency.py
```

---

## 5. Stripe Gateway Mocking

### 5.1 Stripe Checkout Create Mocking
Mock checkout session redirects are simulated by monkeypatching the Stripe SDK. Pytest intercepts the creation call and returns a deterministic mock URL:
```python
# conftest.py
@pytest.fixture
def mock_stripe_checkout(monkeypatch):
    class MockSession:
        id = "cs_test_mock_123"
        url = "https://checkout.stripe.com/c/pay/cs_test_mock_123"
    monkeypatch.setattr("stripe.checkout.Session.create", lambda *args, **kwargs: MockSession())
```

### 5.2 Stripe Webhook Event Simulation
Webhook event verification relies on the `Stripe-Signature` validation header. The tests construct signature headers using the HMAC-SHA256 protocol and the local `STRIPE_WEBHOOK_SECRET` before dispatching payloads to `/api/webhooks/stripe`:

```python
import hmac
import hashlib
import time

def generate_stripe_signature(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    mac = hmac.new(secret.encode('utf-8'), signed_payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"
```

---

## 6. Concurrency Testing Design (Overselling Prevention)

To verify that the application never sells more tickets than available capacities, a concurrent ticket reservation test is implemented in `tests/tier4_scenarios/test_concurrency.py`.

### Mechanism:
1. Create an event with a ticket tier of capacity `N` (e.g., 5).
2. Spawn `M` concurrent threads/requests (e.g., 20) using `ThreadPoolExecutor` or `asyncio.gather` with `httpx.AsyncClient` trying to reserve 1 ticket each simultaneously.
3. Assert that:
   - Exactly `N` requests succeed with a `200 OK` status and return valid reservation sessions.
   - `M - N` requests fail cleanly with a `400 Bad Request` or `422 Unprocessable Entity` specifying inventory is sold out.
   - The total number of tickets locked in database sessions equals exactly `N`.
4. Trigger simulated checkout and webhook confirmation for the `N` successful bookings, confirming that no more than `N` ticket codes are ever issued.
```

---

## Conclusion & Recommendations

1. **Opaque-box verification**: By building the E2E test suite strictly using API endpoints (`httpx.Client`) and HTML content parsers for Jinga2 outputs, we ensure the tests behave identically to production requests.
2. **Deterministic SQLite testing**: Storing tests in a local file-based database (`test_openticket.db`) enables concurrent reads and writes, simulating row-level lock conflicts during high-volume test scenarios.
3. **Robust Webhook Verification**: Using actual HMAC signature verification ensures that signature verification routines are fully tested, exposing configuration issues with secrets early in development.
