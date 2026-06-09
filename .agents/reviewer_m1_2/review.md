## Review Summary

**Verdict**: REQUEST_CHANGES

## Findings

### [Critical] Finding 1: Missing endpoint `GET /api/events/{event_id}/tiers`
- What: The endpoint `GET /api/events/{event_id}/tiers` is completely missing from the routing implementation.
- Where: `src/backend/routes/events.py`
- Why: It violates the interface contract specified in `SCOPE.md`, which defines:
  ```
  ### GET /api/events/{event_id}/tiers
  - Response: List of { id: int, event_id: int, name: str, price: float, capacity: int }
  ```
- Suggestion: Implement the `GET /api/events/{event_id}/tiers` route in `src/backend/routes/events.py` to retrieve all ticket tiers for the specified event ID.

### [Major] Finding 2: Response schema mismatch for ticket reservation
- What: The response from `POST /api/events/{event_id}/reserve` returns the field `id` instead of `booking_session_id`.
- Where: `src/backend/schemas.py` (lines 20-30, `BookingSessionResponse`) and `src/backend/routes/events.py` (line 67)
- Why: The interface contract in `SCOPE.md` states:
  ```
  Response: { booking_session_id: str, expires_at: str, quantity: int, status: str }
  ```
  However, the Pydantic schema `BookingSessionResponse` defines the session identifier field as `id` (`id: str`).
- Suggestion: Update `BookingSessionResponse` (or create a specific reservation response schema) to return `booking_session_id: str` mapped from the database model's `id` field.

### [Minor] Finding 3: Use of deprecated `datetime.utcnow()`
- What: Use of `datetime.utcnow()` which is deprecated in Python 3.12+.
- Where: `src/backend/routes/events.py`, lines 84 and 106
- Why: While not an immediate failure, `datetime.utcnow()` is deprecated and can produce deprecation warnings in modern Python versions.
- Suggestion: Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` (using `from datetime import timezone`) or keep using timezone-naive datetime objects consistently (e.g. `datetime.now()`).

## Verified Claims

- SQLite WAL mode and busy timeout configuration → verified via `view_file` on `src/backend/database.py` → PASS
- SQLite BEGIN IMMEDIATE on transaction begin → verified via `view_file` on `src/backend/database.py` → PASS
- Row-level locking (SELECT FOR UPDATE) on PostgreSQL → verified via `view_file` on `src/backend/routes/events.py` → PASS
- 100% SQL Injection prevention → verified via static analysis of all database queries in `src/backend/routes/events.py` and `database.py` → PASS

## Coverage Gaps

- None.

## Unverified Items

- pytest execution output — command `poetry run pytest` timed out waiting for user permission prompt response (user away / inactive).

---

## Challenge Report

## Challenge Summary

**Overall risk assessment**: MEDIUM

## Challenges

### [High] Challenge 1: Performance degradation and sequential scans on large database size
- **Assumption challenged**: Querying and summing active reservations directly from the `booking_sessions` table scales well.
- **Attack scenario**: As booking history grows over weeks/months, the `booking_sessions` table will accumulate millions of rows. Since there is no explicit database index on `BookingSession.tier_id`, finding active reservations for a given tier will result in a full sequential table scan.
- **Blast radius**: The reservation endpoint `/api/events/{event_id}/reserve` will become extremely slow, leading to database CPU exhaustion and transaction timeouts under load.
- **Mitigation**: Add a database index on `BookingSession.tier_id` (specifically a composite index on `(tier_id, status, expires_at)`). Alternatively, maintain a cached/denormalized counter of reserved and sold tickets directly on the `TicketTier` row, which is already safely locked via `with_for_update()`.

### [Medium] Challenge 2: Clock drift across multi-node deployments
- **Assumption challenged**: Comparing Python-generated `now = datetime.utcnow()` against `BookingSession.expires_at` in database queries is safe across multiple application servers.
- **Attack scenario**: If the backend is scaled horizontally across multiple nodes behind a load balancer, any clock drift between nodes will lead to inconsistent expiration calculations. For example, if Node A is 5 minutes ahead of Node B, Node A might consider a valid reservation on Node B as already expired and allow overselling.
- **Blast radius**: Temporary overselling of tickets beyond the tier's maximum capacity due to timezone or clock synchronization drift.
- **Mitigation**: Use the database's native time function (e.g., `func.now()`) for query comparisons so all nodes rely on a single source of time (the database server).

### [Low] Challenge 3: SQLite network file locking failure
- **Assumption challenged**: SQLite's table-level lock/BEGIN IMMEDIATE will guarantee concurrency safety in all environments.
- **Attack scenario**: If the SQLite database file is hosted on a network share or NFS mount (which is sometimes done in simple containerized deployments), file locking mechanisms might fail or behave incorrectly, causing database corruption or concurrency violations.
- **Blast radius**: DB locking issues and potential data corruption.
- **Mitigation**: Explicitly document that SQLite is only supported for local storage and production workloads must use PostgreSQL.

## Stress Test Results

- Concurrent reservation requests (12 clients, 5 capacity) → expected to successfully reserve 5 slots and return 400 Bad Request for the other 7 → predicted to PASS based on code logic using `with_for_update` and SQLite `BEGIN IMMEDIATE` configuration.

## Unchallenged Areas

- Stripe session integration — the field `stripe_session_id` exists in the model but has no business logic associated with it yet.
