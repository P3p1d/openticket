# Synthesis of E2E Test Infrastructure Design (Milestone 1)

## Consensus
All three Explorers agree on the core technology stack and integration pattern:
1. **Testing Framework**: Use `pytest` with `pytest-asyncio` and `httpx.AsyncClient` to support concurrent API calls.
2. **Stripe Checkout Mocking**: Mock `stripe.checkout.Session.create` to return a deterministic fake checkout URL (`https://checkout.stripe.com/pay/...`) and session ID.
3. **Stripe Webhook Signature Simulation**: Perform E2E signature verification offline by generating SHA-256 HMAC signatures using the configured `STRIPE_WEBHOOK_SECRET` and attaching them in the `Stripe-Signature` header.
4. **Test Organization**: Split the test cases under `tests/` into four distinct directories:
   - `tests/tier1_features/`: isolated happy-path feature checks (>=25 tests).
   - `tests/tier2_boundaries/`: validation checks, boundaries, timeouts, SQL injection, signature checks (>=25 tests).
   - `tests/tier3_integration/`: complete lifecycle flows and branding dynamic updates (>=5 tests).
   - `tests/tier4_scenarios/`: concurrency race conditions and load resiliency checks (>=5 tests).

## Resolved Conflicts / Reconciled Points
1. **FastAPI Client vs. Live Uvicorn Server**:
   - *Conflict*: Explorer 3 recommends using standard FastAPI `TestClient` with dependency overrides, while Explorer 1 and Explorer 2 recommend launching the application in a background process using `uvicorn` (with SQLite WAL mode enabled) to allow true network concurrency.
   - *Resolution*: To verify row-level locks and concurrency protection (`SELECT FOR UPDATE` in database transactions) under high-concurrency presales, a live server setup using `uvicorn` in a background process/thread is essential. In WAL mode, SQLite supports concurrent readers and writers, which is perfect for concurrency testing. We will require the worker to implement a `live_server` fixture that boots the app using a free port in a background process or thread, alongside setting SQLite to WAL mode (`PRAGMA journal_mode=WAL;`) when executing test sessions.

2. **Database Initialization**:
   - We will use a session-scoped database fixture that sets up and drops all database tables on a file-based SQLite database (`test_openticket.db`), cleanly deleting the database and its WAL files after the test session.

## Detailed Directory Layout to Implement
- `tests/conftest.py`: contains database configuration, live server setup, Stripe mocks.
- `tests/pytest.ini`: sets up pytest execution options (asyncio_mode = auto).
- `tests/utils/stripe_helper.py`: utility to generate webhook signature headers and events.
- `tests/tier1_features/`
- `tests/tier2_boundaries/`
- `tests/tier3_integration/`
- `tests/tier4_scenarios/`
