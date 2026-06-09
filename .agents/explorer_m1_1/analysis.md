# Milestone 1: Backend API & Concurrency Control Design

This document details the architectural design and proposed implementation for Milestone 1 (Backend API & Concurrency Control) of the OpenTicket project.

---

## 1. Executive Summary
Milestone 1 establishes the core backend foundation for OpenTicket, providing:
- A stateless FastAPI application.
- A database abstraction layer using SQLAlchemy 2.0 supporting SQLite (default) and PostgreSQL.
- A robust, transactional ticket-booking reservation system using row-level locking (`SELECT FOR UPDATE` / `with_for_update()`) to prevent ticket overselling.
- Complete SQL injection prevention through exclusive use of ORM-parameterized query constructs.
- An automated concurrency-testing strategy using `pytest` to guarantee system integrity under load.

---

## 2. System Architecture & Constraints

### 2.1 Database Compatibility (SQLite & PostgreSQL)
The application must work seamlessly on both SQLite (for local development/testing) and PostgreSQL (for production).
- **PostgreSQL**: Leverages real row-level locking using `SELECT ... FOR UPDATE` via SQLAlchemy's `.with_for_update()`.
- **SQLite**: Does not support native row-level locking (silently ignores `FOR UPDATE`). To prevent concurrent write operations from deadlocking or causing double-allocation, SQLite must be configured to run in **Write-Ahead Logging (WAL)** mode with a busy timeout, and transactions must be initialized with `BEGIN IMMEDIATE`.

### 2.2 SQL Injection Prevention
To ensure the application is secure against SQL injection attacks:
- **Rule**: No raw SQL strings (`text()`), string formatting (`f"SELECT ..."`), or concatenation in database queries.
- **Enforcement**: All database queries must be written using SQLAlchemy 2.0 ORM constructs (e.g., `select(Model).where(Model.attribute == parameter)`).

### 2.3 Reservation Lifecycle & Capacity Calculation
- When a client reserves tickets, a `BookingSession` is created with a `reserved` status and an expiration timestamp (e.g., `expires_at = now + 10 minutes`).
- Under a transaction, the capacity calculation for a tier is:
  $$\text{Available Capacity} = \text{Total Capacity} - \text{Active Reservations}$$
  Where:
  $$\text{Active Reservations} = \sum \text{quantity} \text{ for } \text{BookingSession} \text{ where } (\text{status} = \text{"paid"} \text{ or } (\text{status} = \text{"reserved"} \text{ and } \text{expires\_at} > \text{now}))$$
- This logic is executed under a row-level lock on the `TicketTier` row to serialize capacity evaluations for that tier.

---

## 3. Database Schema Design (SQLAlchemy 2.0)

We define the following schema using SQLAlchemy 2.0 Declarative Mapping.

```python
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    tiers: Mapped[List["TicketTier"]] = relationship(
        "TicketTier", back_populates="event", cascade="all, delete-orphan"
    )

class TicketTier(Base):
    __tablename__ = "ticket_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="tiers")
    bookings: Mapped[List["BookingSession"]] = relationship(
        "BookingSession", back_populates="tier", cascade="all, delete-orphan"
    )
    tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket", back_populates="tier", cascade="all, delete-orphan"
    )

class BookingSession(Base):
    __tablename__ = "booking_sessions"

    # Using string representation of UUID for database engine compatibility (SQLite/PostgreSQL)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tier_id: Mapped[int] = mapped_column(ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="reserved")  # "reserved", "paid", "expired", "cancelled"
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stripe_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="bookings")
    tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket", back_populates="booking_session", cascade="all, delete-orphan"
    )

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier_id: Mapped[int] = mapped_column(ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False)
    booking_session_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("booking_sessions.id", ondelete="SET NULL"), nullable=True
    )
    check_in_code: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="reserved")  # "reserved", "valid", "checked_in", "refunded"

    # Relationships
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="tickets")
    booking_session: Mapped[Optional["BookingSession"]] = relationship("BookingSession", back_populates="tickets")
```

---

## 4. Database Engine Configuration

To support both engines seamlessly, we implement standard SQLite performance tunings (WAL, busy_timeout) and transaction listener configurations for safe local concurrent development.

```python
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openticket.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Allow multi-threaded access for SQLite (required for testing)
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configure SQLite WAL and Timeout options on connection
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

    # Enforce IMMEDIATE transactions on SQLite to prevent write locks deadlocks
    @event.listens_for(engine, "begin")
    def begin_sqlite_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE;")
```

---

## 5. API Schemas & FastAPI Endpoints

### 5.1 Pydantic Schemas

```python
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

# Event Schemas
class EventCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    date: datetime
    location: str = Field(..., max_length=255)

class EventResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    date: datetime
    location: str

    model_config = ConfigDict(from_attributes=True)

# Ticket Tier Schemas
class TicketTierCreate(BaseModel):
    name: str = Field(..., max_length=255)
    price: float = Field(..., gt=0.0)
    capacity: int = Field(..., gt=0)

class TicketTierResponse(BaseModel):
    id: int
    event_id: int
    name: str
    price: float
    capacity: int

    model_config = ConfigDict(from_attributes=True)

# Booking Reservation Schemas
class ReserveRequest(BaseModel):
    tier_id: int
    quantity: int = Field(..., gt=0)

class ReserveResponse(BaseModel):
    booking_session_id: str
    expires_at: datetime
    quantity: int
    status: str

    model_config = ConfigDict(from_attributes=True)
```

### 5.2 API Routes Logic

The routes use a shared helper dependency to yield the DB session and wrap transactions.

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, and_
from datetime import datetime, timedelta
import uuid

router = APIRouter()

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/api/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(event_data: EventCreate, db: Session = Depends(get_db)):
    db_event = Event(
        name=event_data.name,
        description=event_data.description,
        date=event_data.date,
        location=event_data.location
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@router.get("/api/events", response_model=list[EventResponse])
def list_events(db: Session = Depends(get_db)):
    stmt = select(Event)
    return db.execute(stmt).scalars().all()

@router.post("/api/events/{event_id}/tiers", response_model=TicketTierResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_tier(event_id: int, tier_data: TicketTierCreate, db: Session = Depends(get_db)):
    # Verify event exists
    event_exists = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if not event_exists:
        raise HTTPException(status_code=404, detail="Event not found")
    
    db_tier = TicketTier(
        event_id=event_id,
        name=tier_data.name,
        price=tier_data.price,
        capacity=tier_data.capacity
    )
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

@router.get("/api/events/{event_id}/tiers", response_model=list[TicketTierResponse])
def get_ticket_tiers(event_id: int, db: Session = Depends(get_db)):
    # Verify event exists
    event_exists = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if not event_exists:
        raise HTTPException(status_code=404, detail="Event not found")
        
    stmt = select(TicketTier).where(TicketTier.event_id == event_id)
    return db.execute(stmt).scalars().all()

@router.post("/api/events/{event_id}/reserve", response_model=ReserveResponse, status_code=status.HTTP_201_CREATED)
def reserve_tickets(event_id: int, request: ReserveRequest, db: Session = Depends(get_db)):
    # Start transaction explicitly
    # With SQLAlchemy 2.0, the session is already in a transaction context.
    # We query the TicketTier with a FOR UPDATE lock.
    try:
        # 1. Acquire row lock on the ticket tier
        tier_stmt = (
            select(TicketTier)
            .where(TicketTier.id == request.tier_id, TicketTier.event_id == event_id)
            .with_for_update()
        )
        tier = db.execute(tier_stmt).scalar_one_or_none()
        
        if not tier:
            raise HTTPException(status_code=404, detail="Ticket tier not found for this event")
        
        # 2. Calculate active reservations for this tier
        now = datetime.utcnow()
        active_reservations_stmt = (
            select(func.sum(BookingSession.quantity))
            .where(
                BookingSession.tier_id == request.tier_id,
                or_(
                    BookingSession.status == "paid",
                    and_(
                        BookingSession.status == "reserved",
                        BookingSession.expires_at > now
                    )
                )
            )
        )
        active_reserved = db.execute(active_reservations_stmt).scalar() or 0
        
        # 3. Check capacity constraints
        if active_reserved + request.quantity > tier.capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient ticket capacity available"
            )
        
        # 4. Create Booking Session and Ticket entries
        expires_at = now + timedelta(minutes=10)
        booking_session = BookingSession(
            id=str(uuid.uuid4()),
            tier_id=tier.id,
            quantity=request.quantity,
            status="reserved",
            created_at=now,
            expires_at=expires_at
        )
        db.add(booking_session)
        
        # Pre-allocate ticket rows linked to this session
        for _ in range(request.quantity):
            ticket = Ticket(
                tier_id=tier.id,
                booking_session_id=booking_session.id,
                status="reserved"
            )
            db.add(ticket)
        
        db.commit()
        return booking_session

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
```

---

## 6. Concurrency Testing Strategy (pytest)

To verify that the reservation logic is thread-safe and never oversells a tier:
1. Create a ticket tier with capacity $N$.
2. Launch $M$ concurrent reservation requests (where $M > N$) using threading (e.g., `ThreadPoolExecutor`) or `asyncio`.
3. Verify that:
   - Exactly $N$ requests succeed (return HTTP 201).
   - Exactly $M - N$ requests fail (return HTTP 400).
   - The total number of tickets created in the DB matches $N$.
   - The database contains exactly $N$ reserved quantities in active booking sessions.

### Proposed Pytest Implementation

```python
import pytest
import concurrent.futures
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.backend.main import app, get_db
from src.backend.models import Base

# Setup clean database for test suite
TEST_DATABASE_URL = "sqlite:///./test_concurrency.db"

@pytest.fixture(scope="module")
def setup_db():
    # Setup Engine and recreate tables
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield TestingSessionLocal
    
    # Cleanup tables after module tests
    Base.metadata.drop_all(bind=engine)
    import os
    if os.path.exists("test_concurrency.db"):
        os.remove("test_concurrency.db")
    if os.path.exists("test_concurrency.db-wal"):
        os.remove("test_concurrency.db-wal")
    if os.path.exists("test_concurrency.db-shm"):
        os.remove("test_concurrency.db-shm")

def test_concurrent_reservations(setup_db):
    TestingSessionLocal = setup_db
    
    # Override FastAPI dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    # 1. Create Event and Ticket Tier with capacity of 10
    event_response = client.post("/api/events", json={
        "name": "Underground Rave",
        "description": "Techno all night",
        "date": "2026-06-20T22:00:00",
        "location": "Warehouse 13"
    })
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]
    
    tier_response = client.post(f"/api/events/{event_id}/tiers", json={
        "name": "General Admission",
        "price": 25.0,
        "capacity": 10
    })
    assert tier_response.status_code == 201
    tier_id = tier_response.json()["id"]
    
    # 2. Simulate 30 concurrent reservation requests of quantity 1
    num_requests = 30
    results = []
    
    def send_reserve_request():
        # Each thread uses a fresh client call
        with TestClient(app) as tc:
            return tc.post(
                f"/api/events/{event_id}/reserve",
                json={"tier_id": tier_id, "quantity": 1}
            )
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_reserve_request) for _ in range(num_requests)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            
    # 3. Analyze Results
    successes = [r for r in results if r.status_code == 201]
    failures = [r for r in results if r.status_code == 400]
    others = [r for r in results if r.status_code not in (201, 400)]
    
    print(f"Successes: {len(successes)}, Failures: {len(failures)}, Others: {len(others)}")
    
    # Assertions
    assert len(others) == 0, f"Some requests failed with unexpected status codes: {[r.json() for r in others]}"
    assert len(successes) == 10, f"Expected exactly 10 successful reservations, got {len(successes)}"
    assert len(failures) == 20, f"Expected exactly 20 failed reservations, got {len(failures)}"
    
    # Clean dependency overrides
    app.dependency_overrides.clear()
```
