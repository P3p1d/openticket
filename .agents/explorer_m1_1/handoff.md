# Handoff Report — Milestone 1 Backend Design

This handoff report summarizes the findings, architectural decisions, and verification steps for the design of Milestone 1.

## 1. Observation
We observed the requirements and constraints by reading the following documents:
- **`c:\Development\openticket\ORIGINAL_REQUEST.md`** (Lines 12-15):
  > "Build a stateless Python FastAPI backend that manages events, ticket tiers, orders, and tickets. Implement a transactional ticket booking mechanism using database row-level locking (e.g. `SELECT FOR UPDATE` in SQLAlchemy) to guarantee that ticket inventory is never oversold during high-concurrency presales. The database layer must support SQLite (default) and PostgreSQL."
  > "- **SQL Injection Prevention**: Use ORM-parameterized query execution exclusively. Do not write raw SQL strings or use string formatting for queries."
- **`c:\Development\openticket\.agents\orchestrator\PROJECT.md`** (Lines 23-37):
  Shows the routes layout: `src/backend/main.py`, `src/backend/models.py`, `src/backend/database.py`, etc.
  Specifically:
  > "- `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Returns `booking_session_id`, `expires_at`."
- **`c:\Development\openticket\.agents\sub_orch_m1\SCOPE.md`** (Lines 4-18, 28-43):
  Specifies the schemas, endpoints, and response format.
  Specifically:
  > "- **Database Engine**: Supports SQLite (for testing and local dev) and PostgreSQL (via environment variables). ... SQLite uses standard write-ahead logging (WAL) if needed, but PostgreSQL uses real `SELECT FOR UPDATE` row-level locking."
  > "- `POST /api/events/{event_id}/reserve` Request: `{ tier_id: int, quantity: int }` Response: `{ booking_session_id: str, expires_at: str, quantity: int, status: str }` Error: `400 Bad Request` if insufficient capacity."
- **`c:\Development\openticket\requirements.txt`** (Lines 1-11):
  Confirms the project dependencies:
  > `fastapi>=0.110.0`, `sqlalchemy>=2.0.0`, `psycopg2-binary>=2.9.9`, `pytest>=8.0.0`, `httpx>=0.27.0`.

## 2. Logic Chain
- **Step 1**: To guarantee that ticket inventory is never oversold under high concurrency (from `ORIGINAL_REQUEST.md` R1), the booking logic must serialize evaluation of a tier's capacity and reservation execution.
- **Step 2**: Since PostgreSQL supports row-level locking (`SELECT ... FOR UPDATE`), using SQLAlchemy's `.with_for_update()` on the `TicketTier` row locks the tier during the transaction, preventing concurrent transactions from checking/booking tickets for that tier simultaneously.
- **Step 3**: SQLite silently ignores `.with_for_update()`. To ensure SQLite does not suffer from deadlock or double-allocation under concurrent testing, we must configure SQLite to use WAL mode and a `busy_timeout` (using connection listeners) and force all transactions to start in `IMMEDIATE` mode (using the `begin` listener).
- **Step 4**: To prevent SQL injection, all database interactions must construct queries via SQLAlchemy 2.0 ORM expressions rather than raw text or string formatting.
- **Step 5**: To verify this system works correctly, `pytest` must simulate concurrent reservation requests using a `ThreadPoolExecutor` and assert that the total reservations do not exceed capacity.

## 3. Caveats
- Since SQLite does not have real row-level locking, concurrent performance on SQLite will be limited by database-level serialization (`BEGIN IMMEDIATE`). This is acceptable because SQLite is specified for testing and local development only.
- In-memory SQLite (`sqlite:///:memory:`) does not share state across separate connections unless a shared cache is configured. Therefore, file-based SQLite databases (e.g. `test_concurrency.db`) must be used for concurrency testing and subsequently deleted.
- Webhook notifications and Stripe Checkout endpoints (R2) are planned for Milestone 2 and are not implemented or designed here, other than the placeholder `stripe_session_id` in `BookingSession` to enable future integration.

## 4. Conclusion
We have completed the design of Milestone 1. The exact model structure (SQLAlchemy 2.0 style), FastAPI router endpoints, SQLite configuration listeners, and concurrency testing suite layout have been proposed and written in detail to `c:\Development\openticket\.agents\explorer_m1_1\analysis.md`. This proposal satisfies all requirements including SQL injection prevention, SQLite/PostgreSQL engine support, and row-level locking.

## 5. Verification Method
- **Files to Inspect**:
  - `c:\Development\openticket\.agents\explorer_m1_1\analysis.md` (to verify implementation model structures, FastAPI routes, and configurations).
- **Project Test Execution**:
  Once implemented in the next milestones, run:
  ```powershell
  pytest tests/test_concurrency.py
  ```
  The test passes if exactly $N$ reservations succeed (HTTP 201), $M - N$ fail with HTTP 400, and the database contains exactly $N$ tickets.
