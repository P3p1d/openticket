# Handoff Report - Milestone 1 Backend API & Concurrency Control Design

## 1. Observation
We observed the requirements and constraints of the OpenTicket project from the following files in the workspace:
- **`c:\Development\openticket\ORIGINAL_REQUEST.md`** (Lines 12-14):
  > "Build a stateless Python FastAPI backend that manages events, ticket tiers, orders, and tickets. Implement a transactional ticket booking mechanism using database row-level locking (e.g. `SELECT FOR UPDATE` in SQLAlchemy) to guarantee that ticket inventory is never oversold during high-concurrency presales. The database layer must support SQLite (default) and PostgreSQL.
  > - **SQL Injection Prevention**: Use ORM-parameterized query execution exclusively. Do not write raw SQL strings or use string formatting for queries."
- **`c:\Development\openticket\.agents\orchestrator\PROJECT.md`** (Lines 28-38):
  Defines the codebase layout structure:
  > - `src/backend/`
  >   - `src/backend/main.py`: App entry point.
  >   - `src/backend/models.py`: SQLAlchemy database models.
  >   - `src/backend/database.py`: DB engine and session setup.
  >   - `src/backend/routes/`: Router endpoints.
  > - `tests/`: Automated test suite.
- **`c:\Development\openticket\.agents\sub_orch_m1\SCOPE.md`** (Lines 6-18):
  Outlines the transactional booking sequence:
  > "1. Start a transaction.
  > 2. Query the `TicketTier` with `with_for_update()` (row-level lock).
  > 3. Query active bookings/tickets for that tier to compute available capacity...
  > 4. If enough capacity: create `BookingSession` (status `reserved`, with `expires_at`), create `Ticket` entries linked to it, and commit.
  > 5. If not enough capacity: rollback and return a clean 400 Bad Request error."
  And provides the specific routes and their payloads.

---

## 2. Logic Chain
1. **Engine Compatibility**: To satisfy support for SQLite and PostgreSQL simultaneously, the connection string must be configurable via a `DATABASE_URL` environment variable.
2. **Locking Differences**: SQLite does not support native row-level locking (it ignores `SELECT FOR UPDATE`). To ensure concurrency safety in SQLite, write transactions must be serialized using `BEGIN IMMEDIATE`. For PostgreSQL, SQLAlchemy's `with_for_update()` must be used to lock the specific row.
3. **Capacity Tracking**: Dynamically querying the active/paid bookings under the row lock prevents race conditions and prevents storing out-of-sync counters.
4. **FastAPI Endpoints**: Translating the `SCOPE.md` contracts directly into FastAPI endpoints with Pydantic request/response validation guarantees compliance with the API specifications.
5. **Testing**: Running a real Uvicorn server on a free port and firing concurrent HTTP requests via a thread pool in `pytest` confirms that concurrency safeguards prevent overselling and clean 400 errors are returned to the client.

---

## 3. Caveats
- SQLite still blocks other writers globally during a transaction. If write traffic is extremely high, SQLite might experience timeout errors (`sqlite3.OperationalError: database is locked`) if the operation takes longer than the configured timeout (suggested 30 seconds). PostgreSQL handles this gracefully via fine-grained row locks.
- Timeout processing: The database holds temporary reservation sessions that expire after a timeframe. A background clean-up task or query-time filtering is required to release the seats. This proposal uses query-time filtering (checking `expires_at > now` for active reservations), which is stateless and robust.

---

## 4. Conclusion
We have completed a complete design for Milestone 1 Backend API & Concurrency Control, addressing all constraints, database structures, SQL injection prevention, endpoints, and concurrency testing. The design details have been recorded in `c:\Development\openticket\.agents\explorer_m1_3\analysis.md`.

---

## 5. Verification Method
1. Inspect `c:\Development\openticket\.agents\explorer_m1_3\analysis.md` to review the proposed structures.
2. Once the implementer implements this design, verify using:
   ```powershell
   pytest tests/
   ```
   Check that the concurrency tests pass cleanly on both SQLite and PostgreSQL.
