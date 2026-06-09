# Review Report — Milestone 1 Backend API & Concurrency Control

## Review Summary

**Verdict**: REQUEST_CHANGES

---

## Findings

### [Critical] Finding 1: Missing Endpoint `GET /api/events/{event_id}/tiers`

- **What**: The endpoint `GET /api/events/{event_id}/tiers` is completely missing from the routing implementation.
- **Where**: `src/backend/routes/events.py`
- **Why**: This violates the interface contract specified in `SCOPE.md`, which defines:
  ```markdown
  ### `GET /api/events/{event_id}/tiers`
  - Response: List of `{ id: int, name: str, price: float, capacity: int }`
  ```
- **Suggestion**: Implement the missing route in `src/backend/routes/events.py` to retrieve all ticket tiers for a specific event.

### [Major] Finding 2: Response Schema Mismatch for Reservation Route

- **What**: The response from `POST /api/events/{event_id}/reserve` returns `id` instead of `booking_session_id`.
- **Where**: `src/backend/schemas.py` (`BookingSessionResponse` model) and `src/backend/routes/events.py` (line 67-130).
- **Why**: The interface contract in `SCOPE.md` specifies the response structure as:
  ```markdown
  Response: { booking_session_id: str, expires_at: str, quantity: int, status: str }
  ```
  However, the `BookingSessionResponse` Pydantic model names the session identifier `id` instead of `booking_session_id`, and includes extra database fields that are not part of the contract.
- **Suggestion**: Create a dedicated `BookingReservationResponse` schema or update `BookingSessionResponse` to alias/rename `id` to `booking_session_id` and return only the requested fields.

### [Minor] Finding 3: Use of Deprecated `datetime.utcnow()`

- **What**: The code uses `datetime.utcnow()` which is deprecated in Python 3.12+.
- **Where**: `src/backend/routes/events.py`, lines 84 and 106.
- **Why**: While functional, `datetime.utcnow()` generates deprecation warnings in newer versions of Python.
- **Suggestion**: Replace `datetime.utcnow()` with timezone-aware datetime objects using `datetime.now(timezone.utc)` or use timezone-naive `datetime.now()` consistently.

---

## Verified Claims

- **Transaction safety with row-level locking (SELECT FOR UPDATE) on PostgreSQL** → verified via `view_file` on `src/backend/routes/events.py` (lines 70-72) → **PASS**
  - *Details*: The transaction fetches the `TicketTier` row using `select(TicketTier).where(TicketTier.id == request.tier_id).with_for_update()`. This ensures that subsequent capacity verification and ticket creation are serialized on the tier level, preventing double booking.
- **SQLite configuration safety (WAL mode, busy timeout, BEGIN IMMEDIATE)** → verified via `view_file` on `src/backend/database.py` (lines 26-39) → **PASS**
  - *Details*: The SQLite dialect engine is correctly listened to. During `"connect"`, it sets `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=30000`. During `"begin"`, it issues `BEGIN IMMEDIATE` to prevent deadlock and write-lock escalation issues.
- **100% SQL Injection prevention** → verified via static inspection of `src/backend/routes/events.py` and `src/backend/database.py` → **PASS**
  - *Details*: All queries utilize high-level SQLAlchemy 2.0 ORM expressions (`select`, `where`, `and_`, `or_`, `func.sum`) with parameterized values. There are no raw SQL strings or string formatting for query construction.

---

## Coverage Gaps

- **Indices on Foreign Keys** — risk level: **MEDIUM** — recommendation: **Investigate**
  - *Details*: The `BookingSession` table contains a foreign key to `TicketTier` (`tier_id`), but no database index is created on this column. As booking history scales, queries summing up reservations for capacity checks will result in full-table scans.

---

## Unverified Items

- **pytest Execution Output** — the terminal commands failed to execute.
  - *Commands attempted*:
    - `poetry run pytest -v -s`
    - `pytest`
  - *Reason not verified*: Both command executions timed out waiting for user approval because the workspace operates in a headless/automated environment.
  - *Mitigation/Sanity check*: We manually inspected the test file `tests/test_concurrency.py` and confirmed that it spins up a real server, simulates 12 concurrent requests on a capacity-5 tier, and asserts 5 successes and 7 failures, verifying the correct concurrency control behavior.

---

## Challenge Report

### Challenge Summary

**Overall risk assessment**: MEDIUM

### Challenges

#### [High] Challenge 1: Performance degradation/CPU exhaustion under large booking history

- **Assumption challenged**: Querying and summing active reservations directly from the `booking_sessions` table scales well under real production loads.
- **Attack scenario**: As bookings grow to hundreds of thousands or millions of records, querying `BookingSession` by `tier_id` and summing the quantity will require sequential table scans because there is no index on `BookingSession.tier_id`.
- **Blast radius**: The reservation endpoint will become extremely slow, leading to database CPU exhaustion and request timeouts.
- **Mitigation**: Add a database index on `BookingSession.tier_id` or `(tier_id, status, expires_at)`. Better yet, maintain a denormalized `reserved_count` or `sold_count` counter directly on the locked `TicketTier` record.

#### [Medium] Challenge 2: Clock drift across multi-node application server deployments

- **Assumption challenged**: Comparing Python-generated `now = datetime.utcnow()` against database timestamps is reliable.
- **Attack scenario**: If the application server runs on multiple nodes behind a load balancer, any clock drift between servers could cause inconsistent expiration windows or premature ticket expiration.
- **Blast radius**: Slight variations in reservation expiry times, potentially allowing double booking if one node is ahead and another is behind.
- **Mitigation**: Utilize the database's native timestamp function (e.g., `func.now()`) within queries so that all comparison checks refer to the database server's clock.

#### [Low] Challenge 3: SQLite file locking failures on network-attached filesystems

- **Assumption challenged**: SQLite's table-level lock/BEGIN IMMEDIATE will guarantee concurrency safety in all server environments.
- **Attack scenario**: Deploying the backend inside multiple container replicas with a shared SQLite database file hosted on a network share or NFS mount where file locks are not fully POSIX-compliant.
- **Blast radius**: SQLite lock corruption or concurrency failures.
- **Mitigation**: Add a warning/check in documentation that SQLite is strictly for local/development use, and production must use PostgreSQL.

### Stress Test Results

- **Scenario**: 12 parallel reservation requests against a tier of capacity 5.
- **Expected Behavior**: 5 requests succeed (HTTP 201), 7 requests fail (HTTP 400 with insufficient capacity message).
- **Actual/Predicted Behavior**: **PASS** (statically verified: `with_for_update()` locking on PostgreSQL and `BEGIN IMMEDIATE` transaction begin on SQLite guarantee serial execution).

### Unchallenged Areas

- **Stripe session flow**: The field `stripe_session_id` is defined but currently unused in Milestone 1 business logic.
