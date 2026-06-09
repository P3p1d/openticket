# Milestone 1 Backend API & Concurrency Control Design Analysis

This analysis outlines the architecture, database schema, transactional logic, and concurrency test strategy for Milestone 1 of the OpenTicket project.

---

## 1. Database Engine Configurations

OpenTicket must run seamlessly on SQLite (for local development and testing) and PostgreSQL (for production). The engine configuration handles concurrency differences between the two systems.

### SQLite Concurrency Settings
SQLite uses database-level locking for write operations. To allow high-concurrency read-write scenarios without encountering immediate "database is locked" errors, we configure SQLite with:
1. **Write-Ahead Logging (WAL)**: Allows readers to read while a writer is writing.
2. **Busy Timeout**: Sets a wait duration (e.g., 30 seconds) for locks to release rather than immediately throwing an exception.
3. **Immediate Write Transactions**: Forces SQLAlchemy transactions to start with `BEGIN IMMEDIATE` rather than a generic deferred `BEGIN`, preventing concurrent writers from reading outdated state and later deadlocking on writes.

```python
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openticket.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # Set busy timeout (30 seconds)
    connect_args["timeout"] = 30.0

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# Start every SQLite write transaction with BEGIN IMMEDIATE to serialize writes
@event.listens_for(engine, "begin")
def do_begin(conn):
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("BEGIN IMMEDIATE")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### PostgreSQL Concurrency Settings
In PostgreSQL, SQLAlchemy's `.with_for_update()` translates to `SELECT ... FOR UPDATE`, which locks the matched rows (the selected `TicketTier`). This is highly scalable because transactions booking different tiers do not block each other.

---

## 2. Database Schemas & Models

We define the following schemas using SQLAlchemy 2.0 declarative style. 

```python
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import ForeignKey, DateTime, String, Integer, Float, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    
    tiers: Mapped[List["TicketTier"]] = relationship("TicketTier", back_populates="event", cascade="all, delete-orphan")
    bookings: Mapped[List["BookingSession"]] = relationship("BookingSession", back_populates="event")

class TicketTier(Base):
    __tablename__ = "ticket_tiers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    event: Mapped["Event"] = relationship("Event", back_populates="tiers")
    bookings: Mapped[List["BookingSession"]] = relationship("BookingSession", back_populates="tier")
    tickets: Mapped[List["Ticket"]] = relationship("Ticket", back_populates="tier")

class BookingSession(Base):
    __tablename__ = "booking_sessions"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id"), nullable=False)
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket_tiers.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="reserved")  # reserved, paid, cancelled, expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    event: Mapped["Event"] = relationship("Event", back_populates="bookings")
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="bookings")
    tickets: Mapped[List["Ticket"]] = relationship("Ticket", back_populates="booking_session", cascade="all, delete-orphan")

class Ticket(Base):
    __tablename__ = "tickets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_session_id: Mapped[str] = mapped_column(String, ForeignKey("booking_sessions.id"), nullable=False)
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket_tiers.id"), nullable=False)
    ticket_code: Mapped[str] = mapped_column(String, nullable=False, unique=True, default=lambda: f"TC-{uuid.uuid4().hex[:8].upper()}")
    status: Mapped[str] = mapped_column(String, nullable=False, default="reserved")  # reserved, valid, used, refunded
    
    booking_session: Mapped["BookingSession"] = relationship("BookingSession", back_populates="tickets")
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="tickets")
```

---

## 3. Transactional Booking & Row-Level Locking

The reservation process guarantees ticket availability by enforcing the following sequence:

1. **Open Transaction**: A database transaction is initiated.
2. **Lock Ticket Tier Row**: The `TicketTier` is fetched with a write lock using `with_for_update()`. If another concurrent transaction holds the lock, this transaction waits.
3. **Calculate Remaining Capacity**:
   - Calculate all active/paid ticket quantities for the tier.
   - An reservation is *active* if its status is `"paid"` or if it is `"reserved"` and `expires_at` is in the future.
4. **Compare and Allocate**:
   - If `capacity - current_reservations >= requested_quantity`, proceed.
   - Else, rollback transaction and return a `400 Bad Request` HTTP error.
5. **Insert Records**: Insert the `BookingSession` and pre-allocate the corresponding `Ticket` records in `"reserved"` status.
6. **Commit**: Save state and release locks.

### Endpoint Implementation Sketch
```python
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from src.backend.database import get_db
from src.backend.models import TicketTier, BookingSession, Ticket

router = APIRouter()

@router.post("/api/events/{event_id}/reserve", status_code=status.HTTP_200_OK)
def reserve_tickets(event_id: int, payload: ReservationRequest, db: Session = Depends(get_db)):
    try:
        # Acquire row lock (SELECT FOR UPDATE)
        tier_stmt = select(TicketTier).where(
            TicketTier.id == payload.tier_id,
            TicketTier.event_id == event_id
        ).with_for_update()
        tier = db.scalar(tier_stmt)
        
        if not tier:
            db.rollback()
            raise HTTPException(status_code=404, detail="Ticket tier not found")
        
        now = datetime.now(timezone.utc)
        
        # Calculate active bookings (reserved and non-expired, or paid)
        reserved_stmt = select(func.sum(BookingSession.quantity)).where(
            BookingSession.tier_id == tier.id,
            (BookingSession.status == "paid") | 
            ((BookingSession.status == "reserved") & (BookingSession.expires_at > now))
        )
        current_reserved = db.scalar(reserved_stmt) or 0
        
        if tier.capacity - current_reserved < payload.quantity:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient capacity"
            )
            
        expires_at = now + timedelta(minutes=15)
        booking = BookingSession(
            event_id=event_id,
            tier_id=tier.id,
            quantity=payload.quantity,
            status="reserved",
            expires_at=expires_at
        )
        db.add(booking)
        db.flush() # populated booking.id
        
        for _ in range(payload.quantity):
            ticket = Ticket(
                booking_session_id=booking.id,
                tier_id=tier.id,
                status="reserved"
            )
            db.add(ticket)
            
        db.commit()
        
        return {
            "booking_session_id": booking.id,
            "expires_at": expires_at.isoformat(),
            "quantity": booking.quantity,
            "status": booking.status
        }
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction failed: {str(e)}"
        )
```

---

## 4. SQL Injection Prevention

To prevent SQL Injection, **no f-strings, raw SQL strings, or manual interpolations are permitted**. 
All database interactions must be structured with SQLAlchemy 2.0 ORM construct classes:
- Query criteria use `.where()` with model columns: `where(TicketTier.id == tier_id)`
- Aggregate functions use `func` namespace elements: `func.sum(...)`
- Submitting fields as object attributes during insertion/update automatically binds parameters.

---

## 5. API Endpoints & Interfaces

### Pydantic Validation Models
```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class EventCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    date: datetime
    location: str = Field(..., min_length=1)

class EventResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    date: datetime
    location: str

    class Config:
        from_attributes = True

class TicketTierCreate(BaseModel):
    name: str = Field(..., min_length=1)
    price: float = Field(..., ge=0.0)
    capacity: int = Field(..., gt=0)

class TicketTierResponse(BaseModel):
    id: int
    event_id: int
    name: str
    price: float
    capacity: int

    class Config:
        from_attributes = True

class ReservationRequest(BaseModel):
    tier_id: int
    quantity: int = Field(..., gt=0)

class BookingSessionResponse(BaseModel):
    booking_session_id: str
    expires_at: str
    quantity: int
    status: str
```

### Endpoint Declarations
- `POST /api/events` — Create an event (Request: `EventCreate`, Response: `EventResponse`)
- `GET /api/events` — List all events (Response: `List[EventResponse]`)
- `POST /api/events/{event_id}/tiers` — Create a ticket tier for an event (Request: `TicketTierCreate`, Response: `TicketTierResponse`)
- `GET /api/events/{event_id}/tiers` — List all tiers for an event (Response: `List[TicketTierResponse]`)
- `POST /api/events/{event_id}/reserve` — Reserve tickets under a row lock (Request: `ReservationRequest`, Response: `BookingSessionResponse`)

---

## 6. Concurrency Testing Strategy

To verify that the application never oversells capacity, we require an integration test executing simultaneous purchase requests.

### Pytest Concurrency Test Code
The following test runs 20 concurrent threads attempting to buy 1 ticket each on a ticket tier with a capacity of 10. Exactly 10 must succeed and 10 must fail with a `400 Bad Request` error.

We use `ThreadPoolExecutor` from `concurrent.futures` to call the `/reserve` HTTP API endpoint hosted on a live test server.

```python
import pytest
import threading
import time
import socket
from concurrent.futures import ThreadPoolExecutor
import uvicorn
from fastapi import FastAPI
import httpx

from src.backend.database import Base, engine, SessionLocal
from src.backend.models import Event, TicketTier
from src.backend.main import app  # Assuming main.py exports the FastAPI app

# Helper to find an open local port
def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def startup_test_server():
    # Setup test database tables
    Base.metadata.create_all(bind=engine)
    
    # Run uvicorn server in a separate background thread
    port = find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    
    # Wait for server to become active
    time.sleep(1)
    
    yield f"http://127.0.0.1:{port}"
    
    # Teardown
    server.should_exit = True
    thread.join(timeout=5)
    Base.metadata.drop_all(bind=engine)

def test_concurrency_capacity_limits(startup_test_server):
    base_url = startup_test_server
    
    # Create test Event
    event_payload = {
        "name": "Heavy Metal Concert",
        "description": "Concurrently tested concert",
        "date": "2026-12-31T20:00:00Z",
        "location": "Warehouse 9"
    }
    with httpx.Client() as client:
        r_event = client.post(f"{base_url}/api/events", json=event_payload)
        assert r_event.status_code == 200
        event_id = r_event.json()["id"]
        
        # Create Ticket Tier with capacity = 10
        tier_payload = {
            "name": "General Admission",
            "price": 45.0,
            "capacity": 10
        }
        r_tier = client.post(f"{base_url}/api/events/{event_id}/tiers", json=tier_payload)
        assert r_tier.status_code == 200
        tier_id = r_tier.json()["id"]

    # We launch 20 concurrent HTTP request tasks, trying to reserve 1 ticket each
    reserve_url = f"{base_url}/api/events/{event_id}/reserve"
    payload = {"tier_id": tier_id, "quantity": 1}
    
    def send_reserve_request():
        # Each thread uses its own HTTP client connection to prevent reuse blocking
        with httpx.Client() as client:
            try:
                response = client.post(reserve_url, json=payload, timeout=10.0)
                return response.status_code, response.text
            except Exception as ex:
                return 500, str(ex)

    # Execute concurrently
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(send_reserve_request) for _ in range(20)]
        results = [f.result() for f in futures]
        
    # Analyze responses
    successes = [res for res in results if res[0] == 200]
    failures = [res for res in results if res[0] == 400]
    others = [res for res in results if res[0] not in (200, 400)]
    
    # Exactly 10 requests must succeed
    assert len(successes) == 10, f"Expected 10 successes, got {len(successes)}. Results: {results}"
    # Exactly 10 requests must fail with a 400 status code
    assert len(failures) == 10, f"Expected 10 failures (400), got {len(failures)}. Results: {results}"
    # There should be no network or internal server errors
    assert len(others) == 0, f"Expected 0 unexpected errors, got {len(others)}. Details: {others}"
```
