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
