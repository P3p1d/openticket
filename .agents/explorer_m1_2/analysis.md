# Milestone 1 Design & Analysis: Backend API & Concurrency Control

This document outlines the architectural design, database schemas, API routes, and concurrency control mechanism for Milestone 1 of the OpenTicket application.

---

## 1. Requirements & Constraints Analysis

Based on `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `SCOPE.md`, the backend API and concurrency control layer must satisfy the following constraints:

### DB Engine Support: SQLite and PostgreSQL
* **SQLite (Default / Dev)**: Needs to support multi-threaded test environments. SQLite lacks fine-grained row-level locking (`SELECT FOR UPDATE` is ignored/unsupported). To ensure safety and prevent database locked errors, SQLite will be configured to write-ahead logging (WAL) mode, and write transactions will be serialized using `BEGIN IMMEDIATE` (via SQLAlchemy event listeners).
* **PostgreSQL (Production)**: Uses full transactional isolation with row-level locking via `with_for_update()`.

### Concurrency Control & Row-Level Locking
* Under high-concurrency presales, overselling must be strictly prevented.
* Locking sequence:
  1. Acquire a row-level lock on the `TicketTier` row using `with_for_update()`.
  2. Compute the current reserved/sold ticket count for the tier (from active, unexpired, or paid booking sessions).
  3. Compare requested quantity with available capacity (`capacity` - `active_reservations`).
  4. If capacity permits, create a `BookingSession` (status: `"reserved"`) and corresponding `Ticket` entries, then commit.
  5. If capacity is exceeded, rollback the transaction and return an HTTP `400 Bad Request`.
* Locking the parent `TicketTier` row first prevents deadlocks and serializes requests targeting the same tier.

### SQL Injection Prevention
* No raw SQL strings or string formatting (`f"SELECT ..."`).
* Use SQLAlchemy ORM parameterized statements exclusively (e.g., `select(Model).where(...)`).

---

## 2. Proposed Database Schemas & Models

We propose using SQLAlchemy 2.0 type-annotated declarative models (`Mapped` and `mapped_column`) to ensure static analysis compatibility and clean code structure.

### Proposed File: `src/backend/models.py`

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Boolean
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    pass

class Event(Base):
    """
    Represents an event host by OpenTicket.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    date: Mapped[str] = mapped_column(String, nullable=False)  # ISO string or user-friendly date
    location: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tiers: Mapped[list["TicketTier"]] = relationship(
        "TicketTier", back_populates="event", cascade="all, delete-orphan"
    )

class TicketTier(Base):
    """
    Represents a ticket tier (e.g. GA, VIP) for an event with set capacity and price.
    """
    __tablename__ = "ticket_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="tiers")
    bookings: Mapped[list["BookingSession"]] = relationship(
        "BookingSession", back_populates="tier", cascade="all, delete-orphan"
    )

class BookingSession(Base):
    """
    Represents a reservation session for tickets. Holds tickets for a limited time (e.g., 15 mins).
    """
    __tablename__ = "booking_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="reserved", nullable=False)  # "reserved", "paid", "expired", "cancelled"
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="bookings")
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="booking_session", cascade="all, delete-orphan"
    )

class Ticket(Base):
    """
    Represents individual tickets generated under a reservation session.
    """
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_session_id: Mapped[str] = mapped_column(
        String, ForeignKey("booking_sessions.id", ondelete="CASCADE"), nullable=False
    )
    ticket_code: Mapped[str] = mapped_column(String, unique=True, default=lambda: str(uuid.uuid4()), nullable=False)
    is_checked_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    booking_session: Mapped["BookingSession"] = relationship("BookingSession", back_populates="tickets")
```

---

## 3. Database Connection & Engine Setup

To support SQLite (with appropriate WAL mode and transaction serialization) and PostgreSQL, the engine is dynamically initialized based on the environment variables.

### Proposed File: `src/backend/database.py`

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./openticket.db"

    class Config:
        env_file = ".env"

settings = Settings()

# Setup Engine with proper options based on dialect
if settings.DATABASE_URL.startswith("sqlite"):
    # check_same_thread=False is required for SQLite in multi-threaded environments (like FastAPI and pytest concurrency)
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

    # Enable WAL mode for SQLite to support concurrent reads during writes
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    # Automatically force BEGIN IMMEDIATE for all write transactions on SQLite.
    # This prevents mid-transaction database lock contention and deadlocks.
    @event.listens_for(engine, "begin")
    def do_begin(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")
else:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI Dependency for database session injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 4. Proposed Pydantic Schemas

Pydantic schemas ensure strong validation of inputs and output responses.

### Proposed File: `src/backend/schemas.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# Event Schemas
class EventCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    date: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)

class EventResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    date: str
    location: str
    created_at: datetime

    class Config:
        from_attributes = True

# TicketTier Schemas
class TicketTierCreate(BaseModel):
    name: str = Field(..., min_length=1)
    price: float = Field(..., gt=0.0)
    capacity: int = Field(..., gt=0)

class TicketTierResponse(BaseModel):
    id: int
    event_id: int
    name: str
    price: float
    capacity: int

    class Config:
        from_attributes = True

# Booking / Reservation Schemas
class BookingReserveRequest(BaseModel):
    tier_id: int
    quantity: int = Field(..., gt=0)

class BookingReserveResponse(BaseModel):
    booking_session_id: str
    expires_at: datetime
    quantity: int
    status: str

    class Config:
        from_attributes = True
```

---

## 5. API Endpoints & Transaction Booking Logic

Below are the routes handling event and tier creation, listing, and concurrent-safe ticket reservation.

### Proposed File: `src/backend/routes/events.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_
from datetime import datetime, timedelta
from typing import List

from src.backend.database import get_db
from src.backend.models import Event, TicketTier, BookingSession, Ticket
from src.backend.schemas import (
    EventCreate, EventResponse, 
    TicketTierCreate, TicketTierResponse,
    BookingReserveRequest, BookingReserveResponse
)

router = APIRouter()

def reserve_tickets_transactional(db: Session, event_id: int, tier_id: int, quantity: int) -> BookingSession:
    """
    Thread-safe, concurrent-safe transactional ticket reservation logic.
    """
    # 1. Acquire exclusive lock on the specific TicketTier row.
    # This serializes execution of reservations targeting this specific tier.
    stmt = select(TicketTier).where(
        TicketTier.id == tier_id,
        TicketTier.event_id == event_id
    ).with_for_update()
    
    tier = db.execute(stmt).scalar_one_or_none()
    if not tier:
        raise ValueError("Ticket tier not found or does not belong to this event.")

    # 2. Count current active (paid or unexpired reserved) ticket quantities.
    now = datetime.utcnow()
    active_bookings_stmt = select(BookingSession).where(
        BookingSession.tier_id == tier_id,
        or_(
            BookingSession.status == "paid",
            and_(
                BookingSession.status == "reserved",
                BookingSession.expires_at > now
            )
        )
    )
    active_bookings = db.execute(active_bookings_stmt).scalars().all()
    reserved_quantity = sum(b.quantity for b in active_bookings)

    # 3. Verify capacity constraints
    available_capacity = tier.capacity - reserved_quantity
    if quantity > available_capacity:
        raise ValueError("Insufficient ticket capacity available.")

    # 4. Generate Reservation and related Tickets
    expires_at = now + timedelta(minutes=15)
    booking = BookingSession(
        tier_id=tier_id,
        quantity=quantity,
        status="reserved",
        expires_at=expires_at
    )
    db.add(booking)
    db.flush()  # Populate booking.id UUID

    # Pre-generate individual tickets linked to this session
    for _ in range(quantity):
        ticket = Ticket(
            booking_session_id=booking.id,
            is_checked_in=False
        )
        db.add(ticket)

    return booking

@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(event: EventCreate, db: Session = Depends(get_db)):
    db_event = Event(
        name=event.name,
        description=event.description,
        date=event.date,
        location=event.location
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@router.get("/events", response_model=List[EventResponse])
def list_events(db: Session = Depends(get_db)):
    stmt = select(Event)
    return db.execute(stmt).scalars().all()

@router.post("/events/{event_id}/tiers", response_model=TicketTierResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_tier(event_id: int, tier: TicketTierCreate, db: Session = Depends(get_db)):
    event_stmt = select(Event).where(Event.id == event_id)
    db_event = db.execute(event_stmt).scalar_one_or_none()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    db_tier = TicketTier(
        event_id=event_id,
        name=tier.name,
        price=tier.price,
        capacity=tier.capacity
    )
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

@router.get("/events/{event_id}/tiers", response_model=List[TicketTierResponse])
def get_ticket_tiers(event_id: int, db: Session = Depends(get_db)):
    event_stmt = select(Event).where(Event.id == event_id)
    db_event = db.execute(event_stmt).scalar_one_or_none()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    tier_stmt = select(TicketTier).where(TicketTier.event_id == event_id)
    return db.execute(tier_stmt).scalars().all()

@router.post("/events/{event_id}/reserve", response_model=BookingReserveResponse)
def reserve_tickets(event_id: int, req: BookingReserveRequest, db: Session = Depends(get_db)):
    try:
        # reserve_tickets_transactional handles locking and capacity evaluation
        booking = reserve_tickets_transactional(db, event_id, req.tier_id, req.quantity)
        db.commit()
        return booking
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="An error occurred during booking: " + str(e))
```

### Proposed File: `src/backend/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.backend.routes import events
from src.backend.database import engine, Base

# Create DB Tables (Normally run via migrations, but automatically created for M1/Testing)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="OpenTicket Backend API")

# Add CORS Middleware (configured from environments later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok"}
```

---

## 6. Concurrency Testing Strategy

To verify our transactional concurrency control, we must implement an integration test using `pytest` and `ThreadPoolExecutor`.

### Key Elements of the Test:
1. **Background Live Server**: Run `uvicorn` in a background daemon thread bound to a free local port.
2. **File-based Shared Test DB**: Since `:memory:` databases are isolated per connection, configure SQLite to point to a temporary test file (e.g. `test_openticket.db`) which is wiped after the session.
3. **High-Concurrency Hit**: Use `concurrent.futures.ThreadPoolExecutor` to send `N` requests (e.g. 10) to a tier with capacity `C` (e.g. 5) where each request attempts to reserve 1 ticket.
4. **Validation**: Check that exactly `C` requests return `200 OK`, exactly `N - C` requests return `400 Bad Request`, and no database locked or server error exceptions leakage occurs (which would result in `500 Internal Server Error`).

### Proposed File: `tests/test_concurrency.py`

```python
import pytest
import threading
import socket
import time
import os
import httpx
import uvicorn
from concurrent.futures import ThreadPoolExecutor

# Force test database URL in environment before importing app
TEST_DB_FILE = "test_concurrency_openticket.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_FILE}"

from src.backend.main import app
from src.backend.database import engine, Base

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    # Ensure fresh DB tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup DB file after tests
    if os.path.exists(TEST_DB_FILE):
        try:
            os.remove(TEST_DB_FILE)
            # Remove any SQLite WAL/SHM files
            if os.path.exists(f"{TEST_DB_FILE}-wal"):
                os.remove(f"{TEST_DB_FILE}-wal")
            if os.path.exists(f"{TEST_DB_FILE}-shm"):
                os.remove(f"{TEST_DB_FILE}-shm")
        except Exception:
            pass

@pytest.fixture(scope="module")
def live_server():
    port = get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    
    thread = threading.Thread(target=server.run)
    thread.daemon = True
    thread.start()
    
    # Wait for server startup
    time.sleep(0.5)
    
    yield f"http://127.0.0.1:{port}"
    
    server.should_exit = True
    thread.join(timeout=2)

def test_concurrent_presale_preserves_capacity(live_server):
    # 1. Create an Event
    event_payload = {
        "name": "Midnight Rave",
        "description": "Electronic music party",
        "date": "2026-08-20T23:00:00Z",
        "location": "Club Zero"
    }
    resp = httpx.post(f"{live_server}/api/events", json=event_payload)
    assert resp.status_code == 201
    event_id = resp.json()["id"]

    # 2. Create a Ticket Tier with capacity of exactly 5 tickets
    tier_payload = {
        "name": "Early Bird",
        "price": 15.0,
        "capacity": 5
    }
    resp = httpx.post(f"{live_server}/api/events/{event_id}/tiers", json=tier_payload)
    assert resp.status_code == 201
    tier_id = resp.json()["id"]

    # 3. Fire 12 concurrent requests to reserve 1 ticket each (Capacity: 5)
    num_requests = 12
    
    def send_reserve_request():
        try:
            r = httpx.post(
                f"{live_server}/api/events/{event_id}/reserve",
                json={"tier_id": tier_id, "quantity": 1},
                timeout=5.0
            )
            return r.status_code, r.json()
        except Exception as e:
            return 500, {"detail": str(e)}

    # Submit requests concurrently
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(send_reserve_request) for _ in range(num_requests)]
        results = [f.result() for f in futures]

    # 4. Process results
    status_codes = [res[0] for res in results]
    successes = status_codes.count(200)
    failures = status_codes.count(400)
    server_errors = [res for res in results if res[0] not in (200, 400)]

    # Print diagnostics
    print(f"Results of concurrency: Successes={successes}, Failures={failures}, Errors={server_errors}")

    # Assert integrity properties
    assert successes == 5, f"Capacity was 5 but {successes} succeeded. Double booking happened!"
    assert failures == 7, f"Expected 7 failures, but got {failures} failures."
    assert len(server_errors) == 0, f"Encountered unexpected internal server errors: {server_errors}"
```
