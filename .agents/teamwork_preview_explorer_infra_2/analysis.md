# OpenTicket E2E Test Infrastructure Design - Final Analysis

## Executive Summary
This analysis outlines the End-to-End (E2E) testing architecture designed for OpenTicket to guarantee transaction safety, modular payment validation (via signature-verified Stripe checkout/webhooks mocks), underground monospace UI rendering, and script-embeddable purchase widget functionality. The design details a multi-tiered test layout (Tiers 1-4) in `pytest` to support progressive integration and validation.

---

## 1. Test Framework and Environment Setup

### 1.1 Core Components & Dependencies
- **Pytest (>= 8.0.0)**: Chosen for its robust runner, simple fixture design, and scalability.
- **pytest-asyncio**: Required for testing FastAPI's async endpoints and executing simultaneous high-concurrency requests in parallel.
- **httpx**: Replaced default `requests` to enable asynchronous HTTP calls (`AsyncClient`) to mock client requests.
- **stripe**: Replaced stub mocks with signature-matching encryption helpers to maintain actual webhook validation security in test environments.

### 1.2 Database Lifecycle Isolation
To prevent cross-test interference, the database structure must be reset.
- **SQLite vs. PostgreSQL**: Standard unit tests run against local SQLite. However, because standard in-memory SQLite does not fully isolate concurrent connections or support `SELECT FOR UPDATE` locking behavior, the concurrency test suite uses a local file-based SQLite database with **Write-Ahead Logging (WAL)** enabled, or optionally targets a PostgreSQL test database via the `DATABASE_URL` environment variable.
- **Fixture Lifecycle**: A session-scoped `db_engine` creates/drops all schemas, and a function-scoped `db_session` executes all API requests inside isolated transaction spaces which are cleared/reseeded between tests.
- **FastAPI Injection**: Overriding the FastAPI DB dependency via `app.dependency_overrides[get_db] = get_test_db` allows seamless integration without editing the code.

---

## 2. Stripe Checkout & Webhook Mocking Strategy

### 2.1 Mocking Checkout Redirection
- **Mechanism**: The backend calls `stripe.checkout.Session.create` inside the `POST /api/bookings/{booking_session_id}/checkout` controller.
- **Mock Implementation**: Rather than disabling external Stripe SDK calls, a `mock_stripe_checkout` fixture patches `stripe.checkout.Session.create` to return a mock object containing a fake session ID and URL (`https://checkout.stripe.com/pay/...`).
- **Data Integrity**: The mock session links back to the original database reservation via a matching `booking_session_id` inside the Stripe session metadata.

### 2.2 Webhook Signature Simulation
- **Significance**: Standard Stripe integrations verify events using a payload signature header. To verify this contract, we generate cryptographically correct signatures during tests.
- **Implementation**: The test helper `generate_stripe_webhook_signature` reads the JSON webhook payload, computes a SHA-256 HMAC using the configured `STRIPE_WEBHOOK_SECRET`, and appends the signature and timestamp to the header (`Stripe-Signature`).
- **Opaque-Box Validation**: The test client hits `POST /api/webhooks/stripe` with the signed header, fully exercising the cryptographic path of the backend webhook signature validator.

---

## 3. Test Suite Organization

To align with the Milestone scope defined in `sub_orch_e2e/SCOPE.md`, the `tests/` directory is split into four distinct tiers:

### Tier 1: Feature Coverage (Isolation)
- Target: >= 25 test cases verifying the 5 core features in isolation.
- Organization:
  - `test_event_tier_mgmt.py`: Admin panel form submits and Jinja layout schemas.
  - `test_booking_reservations.py`: Reserving a tier, inventory decrement, session expiry.
  - `test_stripe_webhooks.py`: Valid webhook trigger, updating database to `paid`.
  - `test_monospace_ui.py`: HTML verification of minimalist dark-theme styling, monospace branding elements.
  - `test_embeddable_widget.py`: Script serving, dynamic branding colors payload.

### Tier 2: Boundary & Corner Cases
- Target: >= 25 test cases verifying boundary logic, errors, and validation security.
- Organization:
  - `test_booking_concurrency.py`: Parallel reservation limits.
  - `test_reservation_timeouts.py`: Garbage collection of timed-out sessions, ticket releases.
  - `test_validation_errors.py`: Negative capacities, negative pricing, invalid UUIDs.
  - `test_sql_injection.py`: SQL injection validation on path parameters/query inputs.
  - `test_webhook_security.py`: Missing headers, expired timestamps, malformed signatures.

### Tier 3: Cross-Feature Integration
- Target: >= 5 test cases combining modules.
- Organization:
  - `test_booking_lifecycle.py`: Create -> Reserve -> Pay -> Retrieve Ticket.
  - `test_branding_dynamic_updates.py`: Updating admin branding settings -> checking widget/checkout update.
  - `test_reservation_recycle.py`: Hold -> Expire -> Re-hold -> Successful checkout.

### Tier 4: Real-World Scenarios
- Target: >= 5 complex scripts verifying concurrent load and integration.
- Organization:
  - `test_high_concurrency_presale.py`: Multi-threaded reservation request load.
  - `test_widget_embedding_flow.py`: Emulating widget loading, customer buying lifecycle.
  - `test_complete_admin_and_customer_flow.py`: Full admin creation to customer check-in path.

---

## 4. Concurrency & Integrity Design
- To verify that a ticket tier with capacity $N$ does not sell more than $N$ tickets under high load, the E2E suite uses `asyncio.gather` on `httpx.AsyncClient` calls.
- By sending $M$ ($M > N$) concurrent requests to `POST /api/events/{event_id}/reserve`, the suite asserts that:
  1. Exactly $N$ requests return `200 OK` with session details.
  2. Exactly $M - N$ requests fail with `409 Conflict` (or `400 Bad Request`).
  3. The database state shows remaining capacity is exactly `0`.
  4. No duplicate session IDs are created.

---

## 5. Draft Content for `TEST_INFRA.md`
The proposed `TEST_INFRA.md` is drafted in detail and saved to the agent's folder at:
`c:\Development\openticket\.agents\teamwork_preview_explorer_infra_2\proposed_TEST_INFRA.md`

It includes code templates for:
- Session-scoped database engine and transaction rollback fixtures.
- Stripe checkout creation patch.
- Stripe signature cryptographic calculation helper.
- Async concurrent reservation test using `asyncio.gather`.
- Execution instructions for the developers.
