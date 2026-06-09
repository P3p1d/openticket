# OpenTicket E2E Testing Infrastructure

This document outlines the architecture, setup, and execution guidelines for OpenTicket's automated test suite. The test suite is designed as an opaque-box, requirement-driven suite, verifying system integration, reliability, security, and performance.

---

## 1. Testing Philosophy

The testing strategy follows a **dual-track** development methodology. While backend and frontend implementations proceed through their milestones, the E2E test suite verifies behavior purely through public APIs, HTML rendering, and simulated payment gateways:
* **Opaque-Box Verification**: Tests do not access database internals directly unless verifying state post-request. They primarily query HTTP endpoints.
* **Hermetic Runs**: Each test run resets/initializes a test database to prevent cross-test state leakage.
* **Deterministic Payment Flow**: All external dependencies, primarily Stripe, are mocked at the network level or simulated locally to run offline in CODE_ONLY network environments.

---

## 2. Test Framework & Configuration

The test infrastructure is built using the following stack:
* **pytest**: Standard Python test runner.
* **httpx**: A modern HTTP client supporting async requests and connection pooling, critical for concurrency tests.
* **pytest-asyncio**: For writing async test cases.
* **SQLAlchemy**: Test DB models setup and seeding using test engine.

### pytest.ini Configuration
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
log_cli = true
log_cli_level = INFO
markers =
    tier1: Tier 1 - Isolation Feature Coverage tests
    tier2: Tier 2 - Boundary and Corner cases
    tier3: Tier 3 - Cross-Feature Integration tests
    tier4: Tier 4 - Real-world Scenario tests
    concurrency: Load and concurrency tests
```

---

## 3. Stripe Mocking & Webhook Simulation

To maintain high-fidelity payment flow tests in offline (CODE_ONLY) environments, Stripe interaction is split into two parts:

### A. Stripe Checkout Redirection Mocking
When a user initiates checkout (`POST /api/bookings/{booking_session_id}/checkout`), the backend delegates to the `PaymentGateway` interface. In testing:
1. The backend configuration selects a `MockPaymentGateway` instead of the real `StripePaymentGateway`.
2. The `MockPaymentGateway` returns a mock checkout URL, e.g., `http://127.0.0.1:8000/mock-stripe-checkout?session_id=cs_test_mock&booking_session_id=booking_123`.
3. The test suite intercepts this response and extracts the checkout session ID.

### B. Stripe Webhook Simulation (Signing Engine)
Instead of relying on the real Stripe webhook forwarding service, the E2E test client posts directly to `/api/webhooks/stripe`. The backend verifies signatures using `stripe.Webhook.construct_event`. To test signature verification offline:
1. Define a static secret for testing: `STRIPE_WEBHOOK_SECRET=whsec_testsecret`.
2. Construct the webhook payload JSON (representing `checkout.session.completed`).
3. Generate a valid HMAC-SHA256 signature in the test code using the Stripe webhook signature format.
4. Pass the signature in the `Stripe-Signature` header.

#### Signature Generator Helper
```python
import hmac
import hashlib
import time
import json

def generate_stripe_signature(payload_dict: dict, webhook_secret: str) -> str:
    timestamp = str(int(time.time()))
    payload_str = json.dumps(payload_dict)
    
    # Compute signature
    signed_payload = f"{timestamp}.{payload_str}".encode("utf-8")
    signature = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    
    return f"t={timestamp},v1={signature}"
```

---

## 4. Test Suite Organization (Tiers 1-4)

The tests are organized hierarchically under the `tests/` directory:

```
tests/
├── conftest.py                   # Global fixtures (test database, live server, clients)
├── helpers/
│   ├── __init__.py
│   ├── stripe_helper.py          # Stripe payload & signature generator
│   └── db_helper.py              # DB cleanup and seeding utilities
├── tier1_feature_coverage/       # Tier 1: Isolation tests (>= 25 cases)
│   ├── test_event_tier_mgmt.py   # Event/Tier CRUD APIs
│   ├── test_booking_session.py   # Booking reservation APIs and timeouts
│   ├── test_stripe_webhook.py    # Stripe webhook checkout confirmation
│   ├── test_ui_admin.py          # Admin panel HTML and brand customizer
│   └── test_widget.py            # Widget API and script rendering
├── tier2_boundary_corner/        # Tier 2: Boundaries, validation & errors (>= 25 cases)
│   ├── test_reservations_timeout.py # Releasing expired tickets
│   ├── test_concurrency_locking.py # Multi-client race condition tests
│   ├── test_validation_bounds.py  # Negative pricing, over-capacity bookings, missing parameters
│   ├── test_stripe_failures.py    # Invalid webhook signatures, replay attacks
│   └── test_security.py           # SQL injection validation
├── tier3_cross_feature/          # Tier 3: Multi-feature integration (>= 5 cases)
│   ├── test_booking_and_branding.py # Dynamic branding applying to booking flows
│   └── test_payment_timeout_cycle.py # Reserve -> Expire -> Reserve -> Succeed cycle
└── tier4_real_world/             # Tier 4: End-to-end production scenarios (>= 5 cases)
    ├── test_high_volume_presale.py # Simulating high-concurrency ticket release
    └── test_multitenant_isolation.py # Multiple events booking in parallel
```

---

## 5. Concurrency Testing Strategy

A key requirement of OpenTicket is that ticket inventory is never oversold under high concurrency.
1. **Live Server Execution**: FastAPI's `TestClient` is synchronous and blocks in single-threaded tests. To verify database row-level locking (e.g. `SELECT FOR UPDATE` in PostgreSQL or serialization in SQLite), the test suite launches `uvicorn` in a background subprocess or thread.
2. **SQLite WAL Mode**: During tests using SQLite, the test database is set to Write-Ahead Logging (WAL) to allow concurrent readers and a writer.
3. **Concurrent Async Requests**: The test runner uses `asyncio.gather` and `httpx.AsyncClient` to send concurrent reservation requests to the live server.
4. **Validation**: For a ticket tier with a capacity of $N$, if $M$ ($M > N$) concurrent requests are made, the test asserts that exactly $N$ bookings succeed (HTTP 200/201) and $M-N$ bookings fail (HTTP 400/409) with appropriate error messages.

---

## 6. Running the Test Suite

### Environment Setup
Create a `.env.test` file or set the environment variables inline:
```bash
TEST_DATABASE_URL=sqlite:///./test_openticket.db
STRIPE_API_KEY=sk_test_mockkey
STRIPE_WEBHOOK_SECRET=whsec_testsecret
```

### Execution Commands
* Run all tests:
  ```bash
  pytest
  ```
* Run a specific tier:
  ```bash
  pytest -m tier1
  pytest -m tier2
  ```
* Run with console logs enabled:
  ```bash
  pytest -s
  ```
