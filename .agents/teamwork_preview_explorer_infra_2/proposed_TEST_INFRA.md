# OpenTicket E2E Test Infrastructure Design

This document details the design, configuration, and execution guidelines for the OpenTicket End-to-End (E2E) test suite. The test suite is designed to be **opaque-box** and **requirement-driven**, ensuring high-concurrency safety, robust modular payment flows (Stripe integration), custom branding layout compliance, and embeddable widget functionality.

---

## 1. Test Runner & Environment Setup

### 1.1 Test Runner & Core Libraries
The testing infrastructure utilizes `pytest` as the test runner, configured with asynchronous testing support.

- **pytest (>= 8.0.0)**: Main test runner and fixture provider.
- **pytest-asyncio (>= 0.23.0)**: Supports asynchronous test execution and async fixtures.
- **httpx (>= 0.27.0)**: Used for making asynchronous HTTP requests to the FastAPI application.
- **stripe (>= 8.0.0)**: Provides Stripe API types and signature helpers to generate cryptographically valid mock webhooks.

### 1.2 Test Configuration (`pytest.ini`)
Create `pytest.ini` in the project root to configure the python paths, async mode, and test markers:

```ini
[pytest]
pythonpath = src
testpaths = tests
asyncio_mode = auto
markers =
    tier1: Feature coverage tests (isolation)
    tier2: Boundary, negative, and error cases
    tier3: Cross-feature integration scenarios
    tier4: Real-world user scenario & concurrency tests
```

### 1.3 Test Environment Variables (`.env.test`)
For local E2E test isolation, environment configurations must be specified to separate the test database, mock Stripe credentials, and timing thresholds:

```env
ENV=testing
DATABASE_URL=sqlite+aiosqlite:///./test_openticket.db
STRIPE_API_KEY=sk_test_mockkey
STRIPE_WEBHOOK_SECRET=whsec_testsecret
RESERVATION_TIMEOUT_SECONDS=5
PORT=8001
```

---

## 2. Test Database Lifecycle & Isolation

### 2.1 Schema Initialization & Cleanup
To run tests in isolation, each test run (or test case) must initialize the database schema and wipe any stale data. 

With SQLite, using an in-memory database (`sqlite+aiosqlite:///:memory:`) is suitable for isolated single-threaded unit tests but has limitations for concurrent transactions. For E2E concurrency testing with transactional locks (`SELECT FOR UPDATE`), we use a local SQLite database file in **Write-Ahead Logging (WAL)** mode or a dedicated PostgreSQL test container.

```python
# File: tests/conftest.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.backend.database import Base, get_db
from src.backend.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_openticket.db"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def db_engine():
    # Setup test engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"timeout": 15} if "sqlite" in TEST_DATABASE_URL else {}
    )
    
    # Configure WAL mode for SQLite to handle concurrency
    if "sqlite" in TEST_DATABASE_URL:
        async with engine.begin() as conn:
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture(scope="function")
async def db_session(db_engine):
    """Provides an isolated session and rolls back transactions after each test."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        # Clean data between tests
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
```

### 2.2 Dependency Injection Override
FastAPI allows overriding the database session dependency during testing.

```python
# File: tests/conftest.py (continued)
@pytest.fixture(scope="function", autouse=True)
async def override_dependencies(db_session):
    async def get_test_db():
        yield db_session
    app.dependency_overrides[get_db] = get_test_db
    yield
    app.dependency_overrides.clear()
```

---

## 3. Stripe Checkout & Webhook Mocking

### 3.1 Mocking Stripe Checkout Creation
To test the checkout flow opaque-box, the endpoint `POST /api/bookings/{booking_session_id}/checkout` must return a Stripe checkout redirect URL. In E2E tests, the external call to Stripe is mocked using `unittest.mock.patch` to avoid hitting live Stripe servers.

```python
# File: tests/conftest.py (continued)
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_stripe_checkout():
    """Mock the stripe.checkout.Session.create method."""
    with patch("stripe.checkout.Session.create") as mock_create:
        mock_session = MagicMock()
        mock_session.id = "cs_test_mocksessionid_123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_mocksessionid_123"
        mock_create.return_value = mock_session
        yield mock_create
```

### 3.2 Simulating Stripe Webhooks with Valid Signatures
To verify webhook processing opaque-box without disabling security controls, the test client computes a valid cryptographic signature using the test webhook secret (`STRIPE_WEBHOOK_SECRET`).

```python
# File: tests/helpers.py
import json
import time
import stripe

def generate_stripe_webhook_signature(payload_dict: dict, secret: str) -> str:
    """
    Computes a valid Stripe-Signature header value for a given payload and secret.
    """
    payload_str = json.dumps(payload_dict)
    timestamp = int(time.time())
    
    # Calculate signature using Stripe SDK's built-in cryptographic helper
    sig = stripe.WebhookSignature.compute_signature(
        payload_str, secret
    )
    return f"t={timestamp},v1={sig}"
```

### 3.3 Example End-to-End Payment Test Case
```python
# File: tests/tier1_feature_coverage/test_stripe_webhooks.py
import pytest
import httpx
from tests.helpers import generate_stripe_webhook_signature

@pytest.mark.asyncio
async def test_stripe_webhook_flow(client, mock_stripe_checkout):
    # 1. Create temporary event and tier (assume API endpoint exists)
    event_res = await client.post("/api/admin/events", json={
        "name": "Underground Techno Night",
        "description": "Industrial minimal beats",
        "tiers": [{"name": "Early Bird", "price": 2500, "capacity": 100}]
    })
    event = event_res.json()
    tier_id = event["tiers"][0]["id"]
    
    # 2. Reserve a ticket (returns booking session)
    reserve_res = await client.post(f"/api/events/{event['id']}/reserve", json={
        "tier_id": tier_id,
        "quantity": 1
    })
    booking = reserve_res.json()
    booking_id = booking["booking_session_id"]
    
    # 3. Request checkout URL
    checkout_res = await client.post(f"/api/bookings/{booking_id}/checkout")
    assert checkout_res.status_code == 200
    assert "checkout_url" in checkout_res.json()
    assert checkout_res.json()["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_mocksessionid_123"
    
    # 4. Construct Stripe Webhook payload (checkout.session.completed)
    webhook_payload = {
        "id": "evt_test_completed_123",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_mocksessionid_123",
                "metadata": {
                    "booking_session_id": booking_id
                },
                "payment_status": "paid",
                "amount_total": 2500,
                "currency": "usd",
                "customer_details": {
                    "email": "raver@example.com",
                    "name": "Alice Rave"
                }
            }
        }
    }
    
    # Generate authentic signature using test webhook secret
    secret = "whsec_testsecret"
    signature = generate_stripe_webhook_signature(webhook_payload, secret)
    
    # 5. POST to webhook endpoint
    webhook_res = await client.post(
        "/api/webhooks/stripe",
        json=webhook_payload,
        headers={"Stripe-Signature": signature}
    )
    assert webhook_res.status_code == 200
    
    # 6. Verify booking completed and check-in code generated
    order_res = await client.get(f"/api/bookings/{booking_id}")
    assert order_res.status_code == 200
    assert order_res.json()["status"] == "paid"
    assert len(order_res.json()["tickets"]) == 1
    assert "check_in_code" in order_res.json()["tickets"][0]
```

---

## 4. Test Suite Organization

To fulfill the rigorous E2E requirements across all planned milestones, the test suite is partitioned into four distinct tiers:

```
tests/
├── conftest.py                             # Async client, database session engines, Stripe patches
├── helpers.py                              # Webhook signatures, test model seeders
├── tier1_feature_coverage/                 # >= 25 tests targeting the 5 key features in isolation
│   ├── test_event_tier_mgmt.py             # Event/Tier creation, retrieval, updates (Admin Panel & APIs)
│   ├── test_booking_reservations.py        # Booking sessions, initial seat holds, remaining capacity responses
│   ├── test_stripe_webhooks.py             # Stripe checkout URL creation and webhook signature validation
│   ├── test_monospace_ui.py                # Jinja2 Layout renders, high-contrast dark theme, branding variables in HTML
│   └── test_embeddable_widget.py           # Static JS serving, widget data fetching endpoints, branding CSS rules injection
├── tier2_boundary_corner/                  # >= 25 tests targeting edge cases, bounds, and security checks
│   ├── test_booking_concurrency.py         # DB-level row-locking validation (preventing overselling)
│   ├── test_reservation_timeouts.py        # Expired reservations auto-releasing capacity after timeout
│   ├── test_validation_errors.py           # Negative capacity/price inputs, incorrect format parameters, overflows
│   ├── test_sql_injection.py               # ORM protection checks (safe handling of single quotes, SQL commands in paths)
│   └── test_webhook_security.py            # Invalid Stripe signatures, replay attacks, missing fields
├── tier3_cross_feature/                    # >= 5 tests combining multiple distinct features
│   ├── test_booking_lifecycle.py           # Create -> Configure branding -> Reserve -> Pay -> Retrieve Ticket -> Validate Code
│   ├── test_branding_dynamic_updates.py    # Update brand config in Admin -> confirm immediately updated UI & widget stylesheet
│   ├── test_reservation_recycle.py         # Hold tickets -> expire -> re-hold released tickets -> complete purchase
│   └── test_admin_order_monitoring.py      # Event purchases dynamically reflecting on admin metrics dashboard
└── tier4_real_world/                       # >= 5 tests verifying full production-like user workflows
    ├── test_high_concurrency_presale.py    # Simulation of simultaneous load exceeding capacity (concurrency control)
    ├── test_widget_embedding_flow.py       # Simulates embedding JavaScript widget loading and completing user reservation
    └── test_complete_admin_and_customer_flow.py # Full event creator, buyer, and venue door check-in workflow
```

---

## 5. Concurrency & Integrity Testing

To prevent ticket overselling, SQLAlchemy row-level locking (`SELECT FOR UPDATE`) is verified under simulated load.

### 5.1 Concurrency Test Design
The concurrency test fires multiple simultaneous booking requests. It verifies that for a tier of capacity $N$, exactly $N$ reservations succeed and the remaining $M - N$ fail with clean client errors (e.g., `409 Conflict`), maintaining total database integrity.

```python
# File: tests/tier4_real_world/test_high_concurrency_presale.py
import pytest
import asyncio
import httpx

@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_oversell(client):
    # 1. Create an event with a limited capacity tier of 5 tickets
    event_res = await client.post("/api/admin/events", json={
        "name": "Underground Concurrency Rave",
        "description": "Strict limited capacity",
        "tiers": [{"name": "General Admission", "price": 1000, "capacity": 5}]
    })
    event = event_res.json()
    tier_id = event["tiers"][0]["id"]
    
    # 2. Spawn 20 concurrent reservation requests (1 ticket each)
    async def attempt_reservation():
        async with httpx.AsyncClient(app=client.app, base_url="http://test") as ac:
            return await ac.post(
                f"/api/events/{event['id']}/reserve",
                json={"tier_id": tier_id, "quantity": 1}
            )
            
    tasks = [attempt_reservation() for _ in range(20)]
    responses = await asyncio.gather(*tasks)
    
    # 3. Analyze responses
    successes = [r for r in responses if r.status_code == 200]
    failures = [r for r in responses if r.status_code in (400, 409, 429)]
    
    # Exactly 5 should succeed
    assert len(successes) == 5
    # The other 15 should fail gracefully
    assert len(failures) == 15
    
    # 4. Verify DB inventory state
    event_status = await client.get(f"/api/events/{event['id']}")
    assert event_status.json()["tiers"][0]["remaining_capacity"] == 0
```

---

## 6. How to Run the Test Suite

### 6.1 Run all tests
```bash
pytest
```

### 6.2 Run a specific tier (using markers)
To run only feature-coverage tests:
```bash
pytest -m tier1
```

To run boundary and concurrency tests:
```bash
pytest -m tier2
```

### 6.3 Run tests with Postgres
To verify database compatibility with PostgreSQL, run tests with the target PostgreSQL database URL:
```bash
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/openticket_test"
pytest
```
