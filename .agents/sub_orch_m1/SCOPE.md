# Scope: Milestone 1 - Backend API & Concurrency Control

## Architecture
We are building a stateless FastAPI backend using SQLAlchemy ORM (SQLAlchemy 2.0 style) to support SQLite and PostgreSQL.
- **Database Engine**: Supports SQLite (for testing and local dev) and PostgreSQL (via environment variables). SQLite uses standard write-ahead logging (WAL) if needed, but PostgreSQL uses real `SELECT FOR UPDATE` row-level locking. For SQLite, since it has limited row-level locking, we should fallback or use table-level locking/serialized transactions, or ensure our queries use the locking flags (which SQLAlchemy translates to nothing/noop on SQLite, but we verify transaction isolation).
- **Concurrency Control**: Under a transaction, when a user requests reservation of `Q` tickets for a tier:
  1. Start a transaction.
  2. Query the `TicketTier` with `with_for_update()` (row-level lock).
  3. Query active bookings/tickets for that tier to compute available capacity. Or keep a counter on the tier (e.g. `reserved_count`, `sold_count` or check tickets/bookings dynamically). Under row-level lock on the `TicketTier` row, checking `capacity` vs (already sold + currently reserved) ensures safety.
  4. If enough capacity: create `BookingSession` (status `reserved`, with `expires_at`), create `Ticket` entries linked to it, and commit.
  5. If not enough capacity: rollback and return a clean 400 Bad Request error.
- **SQL Injection Prevention**: All queries must use SQLAlchemy ORM constructs (e.g. `select(Model).where(...)`) and parameterized input. No raw SQL or format strings.
- **API Endpoints**:
  - `POST /api/events`: Create an event (admin/test utility).
  - `GET /api/events`: List all events.
  - `POST /api/events/{event_id}/tiers`: Create a ticket tier for an event.
  - `GET /api/events/{event_id}/tiers`: Get ticket tiers for an event.
  - `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Request body: `{tier_id: UUID/int, quantity: int}`. Returns: `{booking_session_id: UUID, expires_at: datetime}`.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | DB & Models | Define database schemas and engine configuration in SQLAlchemy. | None | DONE |
| 2 | Booking Logic | Implement transactional booking logic with `with_for_update()` locking. | M1.1 | DONE |
| 3 | API Endpoints | Implement FastAPI routes for events, tiers, and bookings. | M1.2 | DONE |
| 4 | Verification | Write pytest suite simulating concurrent requests and verifying capacity limits. | M1.3 | IN_PROGRESS |

## Interface Contracts
### `POST /api/events`
- Request: `{ name: str, description: str, date: str, location: str }`
- Response: `{ id: int, name: str, description: str, date: str, location: str }`

### `POST /api/events/{event_id}/tiers`
- Request: `{ name: str, price: float, capacity: int }`
- Response: `{ id: int, event_id: int, name: str, price: float, capacity: int }`

### `GET /api/events/{event_id}/tiers`
- Response: List of `{ id: int, name: str, price: float, capacity: int }`

### `POST /api/events/{event_id}/reserve`
- Request: `{ tier_id: int, quantity: int }`
- Response: `{ booking_session_id: str, expires_at: str, quantity: int, status: str }`
- Error: `400 Bad Request` if insufficient capacity.
