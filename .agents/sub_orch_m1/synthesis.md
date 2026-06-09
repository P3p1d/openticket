# Synthesis of Explorer Findings for Milestone 1

Based on the analysis reports from the Explorers, we have unified the design for Milestone 1.

## 1. Database Configuration (`src/backend/database.py`)
- Standard SQLAlchemy engine setup.
- SQLite support:
  - Enforce `check_same_thread=False`.
  - Enable Write-Ahead Logging (WAL) and set a 30-second busy timeout.
  - Automatically intercept engine `begin` events to execute `BEGIN IMMEDIATE` for SQLite. This prevents deadlocks and serializes writes at the SQLite level.
- PostgreSQL support: Uses `psycopg2` under standard engine pools.
- Thread-safe `get_db` generator to manage session lifecycles.

## 2. SQLAlchemy Models (`src/backend/models.py`)
- **`Event`**:
  - `id`: int (PK, autoincrement)
  - `name`: str
  - `description`: str (nullable)
  - `date`: datetime (timezone naive or UTC)
  - `location`: str
- **`TicketTier`**:
  - `id`: int (PK, autoincrement)
  - `event_id`: int (FK `events.id` on delete CASCADE)
  - `name`: str
  - `price`: float
  - `capacity`: int
- **`BookingSession`**:
  - `id`: str (PK, UUID, generated via `uuid.uuid4`)
  - `tier_id`: int (FK `ticket_tiers.id` on delete CASCADE)
  - `quantity`: int
  - `status`: str (default `"reserved"`, can be `"paid"`, `"expired"`, `"cancelled"`)
  - `created_at`: datetime (default current UTC time)
  - `expires_at`: datetime (typically `created_at` + 10-15 minutes)
  - `stripe_session_id`: str (nullable)
- **`Ticket`**:
  - `id`: int (PK, autoincrement)
  - `booking_session_id`: str (FK `booking_sessions.id` on delete CASCADE)
  - `tier_id`: int (FK `ticket_tiers.id` on delete CASCADE)
  - `ticket_code`: str (unique, generated via hex UUID)
  - `status`: str (default `"reserved"`, can be `"valid"`, `"checked_in"`, `"refunded"`)

## 3. Concurrency Locking & Reservation Logic (`src/backend/routes/events.py`)
- Route: `POST /api/events/{event_id}/reserve`
- Inside a transaction block:
  1. Fetch `TicketTier` with `.with_for_update()` lock.
  2. Query `BookingSession` to sum up active quantities for the `tier_id`:
     - Active if `status == 'paid'` or (`status == 'reserved'` and `expires_at > now`).
     - Query is strictly ORM-parameterized:
       ```python
       select(func.sum(BookingSession.quantity)).where(
           BookingSession.tier_id == tier_id,
           or_(
               BookingSession.status == "paid",
               and_(
                   BookingSession.status == "reserved",
                   BookingSession.expires_at > now
               )
           )
       )
       ```
  3. If `active_reservations + requested_quantity > tier.capacity`, rollback and raise `HTTPException(status_code=400, detail="Insufficient ticket capacity available")`.
  4. Otherwise, create `BookingSession` and pre-allocate `Ticket` rows in `"reserved"` status. Commit transaction and return response.

## 4. API Schemas (`src/backend/schemas.py`)
- Event create/response models.
- TicketTier create/response models.
- Booking reservation request/response models.

## 5. Concurrency Test Suite (`tests/test_concurrency.py`)
- Run a live FastAPI server in a background thread using `uvicorn`.
- Create an event and a tier with a small capacity (e.g., 5).
- Spawn a `ThreadPoolExecutor` with concurrent requests (e.g., 10 or 12 requests of quantity 1).
- Validate that exactly 5 succeed (HTTP 201 or 200) and the rest fail (HTTP 400).
- Verify database state matches the expected counts.
