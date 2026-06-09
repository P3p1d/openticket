# Handoff Report — Explorer 2 (Milestone 1)

This report presents the design and analysis of the Backend API and Concurrency Control for OpenTicket (Milestone 1).

## 1. Observation
We examined the workspace files using directory listing and file viewer tools. The key observed requirements are:

* **File: `c:\Development\openticket\ORIGINAL_REQUEST.md`**
  * Lines 12–14: "Build a stateless Python FastAPI backend that manages events, ticket tiers, orders, and tickets. Implement a transactional ticket booking mechanism using database row-level locking (e.g. `SELECT FOR UPDATE` in SQLAlchemy) to guarantee that ticket inventory is never oversold during high-concurrency presales. The database layer must support SQLite (default) and PostgreSQL."
  * Line 14: "- **SQL Injection Prevention**: Use ORM-parameterized query execution exclusively. Do not write raw SQL strings or use string formatting for queries."
  * Lines 34–36: "- [ ] Include an integration test that simulates concurrent ticket purchases (using threading/multiprocessing or asyncio) to verify that a ticket tier with a capacity of N does not sell more than N tickets, returning clean error responses to overflow requests."
* **File: `c:\Development\openticket\.agents\orchestrator\PROJECT.md`**
  * Lines 23–26: Interfaces include `/api/events/{event_id}/reserve` (returns `booking_session_id`, `expires_at`), `/api/bookings/{booking_session_id}/checkout`, and `/api/webhooks/stripe`.
  * Lines 28–38: Project layout defines `src/backend/main.py`, `src/backend/models.py`, `src/backend/database.py`, `src/backend/routes/`, and `tests/`.
* **File: `c:\Development\openticket\.agents\sub_orch_m1\SCOPE.md`**
  * Lines 13–18: Endpoints to implement for M1: `POST /api/events`, `GET /api/events`, `POST /api/events/{event_id}/tiers`, `GET /api/events/{event_id}/tiers`, and `POST /api/events/{event_id}/reserve`.
  * Lines 4–12: Concurrency design highlights using `with_for_update()` on `TicketTier` to lock the tier row. It also mentions SQLite's lack of row-level locking, suggesting transaction-level serialization / WAL mode.
* **File: `c:\Development\openticket\requirements.txt`**
  * Includes `fastapi>=0.110.0`, `sqlalchemy>=2.0.0`, `pydantic-settings>=2.2.0`, `pytest>=8.0.0`, and `httpx>=0.27.0`.

## 2. Logic Chain
1. **Concurrency Control Strategy**: To prevent overselling, transaction execution must be serialized when checking capacity and committing reservations. Using `with_for_update()` in a standard PostgreSQL transaction locks the `TicketTier` row of the requested tier, blocking other concurrent request threads until the transaction commits or rolls back (Observation: `SCOPE.md`, lines 6-11).
2. **SQLite Adaptation**: SQLite does not support row-level locks. If multiple threads concurrently run `SELECT` followed by `INSERT` under a standard `BEGIN DEFERRED` transaction, they will cause `database is locked` exceptions or race conditions. To resolve this:
   - Configure SQLite to Write-Ahead Logging (`PRAGMA journal_mode=WAL`) to allow concurrent reads while a write transaction is active.
   - Use SQLAlchemy's `begin` event listener to run `BEGIN IMMEDIATE` for SQLite transactions. This acquires a write lock at the start of the transaction, serializing bookings on SQLite and preventing deadlocks (Observation: `SCOPE.md`, line 5).
3. **Database Relationships**: A booking session must hold tickets for a tier. We need:
   - `Event` -> `TicketTier` (One-to-Many)
   - `TicketTier` -> `BookingSession` (One-to-Many)
   - `BookingSession` -> `Ticket` (One-to-Many)
   Using SQLAlchemy 2.0 type-annotated declarations ensures type safety and clean schemas (Observation: `requirements.txt` line 3).
4. **Testing Strategy**: To verify concurrency safety under real-world conditions, we need to test concurrent web requests. A standard `FastAPI TestClient` is synchronous and does not simulate thread-concurrency over HTTP. The proposed solution starts a live `uvicorn` instance in a daemon thread on a dynamic local port and targets it using `ThreadPoolExecutor` with concurrent `httpx` client requests (Observation: `ORIGINAL_REQUEST.md`, lines 34-36).

## 3. Caveats
* **PostgreSQL Testing**: The current design focuses on testing using SQLite since it is the default engine, but it is built to support PostgreSQL. In production/CI, PostgreSQL should be tested by setting `DATABASE_URL` in the environment to point to a real Postgres instance.
* **SQLite File locking**: The concurrency test uses a temporary file-based SQLite database (`test_concurrency_openticket.db`) because an in-memory database (`sqlite:///:memory:`) is private to each database connection and cannot easily be accessed concurrently across different threads.
* **Stripe Timeout**: Cleanup of expired ticket reservations is designed for Milestone 2, but the DB structure contains the necessary `expires_at` and `status` fields to support this timeout reservation model.

## 4. Conclusion
We have completed a comprehensive architectural design for Milestone 1:
* Fully structured `src/backend/models.py` using SQLAlchemy 2.0 type annotations.
* Concurrency-safe `src/backend/database.py` that configures WAL mode and `BEGIN IMMEDIATE` transactions on SQLite, and supports PostgreSQL.
* Route handlers in `src/backend/routes/events.py` wrapping ticket reservations in `with_for_update()` transactions.
* A complete `pytest` concurrency test script in `tests/test_concurrency.py` simulating 12 concurrent requests for a capacity of 5 tickets, checking that exactly 5 succeed and 7 fail with `400 Bad Request` without database deadlock or error leakage.

The design is detailed in the file `c:\Development\openticket\.agents\explorer_m1_2\analysis.md`.

## 5. Verification Method
Verify the findings and design by inspecting the following files:
* `c:\Development\openticket\.agents\explorer_m1_2\analysis.md` (Design and proposed implementation details).
* `c:\Development\openticket\.agents\explorer_m1_2\BRIEFING.md` (State, decisions, and constraints mapping).

Once the implementer writes these files, the design can be validated by running the test suite:
```powershell
pytest -v -s tests/test_concurrency.py
```
This command must show exactly 5 successful reservations and 7 rejected requests, and report no internal server errors (500s).
