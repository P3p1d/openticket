import uuid
import random
import string
from datetime import datetime, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session

from src.backend.database import get_db
from src.backend.models import Event, TicketTier, BookingSession, Ticket, SystemSetting

def generate_unique_ticket_code(db: Session) -> str:
    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == "ticket_code_type")
    ).scalar_one_or_none()
    code_type = setting.value if setting else "alphanumeric_8"
    
    attempts = 0
    while attempts < 100:
        if code_type == "numeric_6":
            code = "".join(random.choices(string.digits, k=6))
        else: # default alphanumeric_8
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
        stmt = select(Ticket).where(Ticket.ticket_code == code)
        exists = db.execute(stmt).scalar()
        if not exists:
            return code
        attempts += 1
        
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

from src.backend.schemas import (
    EventCreate,
    EventResponse,
    TicketTierCreate,
    TicketTierResponse,
    BookingReservationRequest,
    BookingSessionResponse,
)

router = APIRouter(prefix="/api/events", tags=["events"])

@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(event_in: EventCreate, db: Session = Depends(get_db)):
    db_event = Event(
        name=event_in.name,
        description=event_in.description,
        date=event_in.date,
        location=event_in.location,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@router.get("", response_model=List[EventResponse])
def get_events(db: Session = Depends(get_db)):
    stmt = select(Event)
    result = db.execute(stmt)
    return result.scalars().all()

@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    stmt = select(Event).where(Event.id == event_id)
    db_event = db.execute(stmt).scalar_one_or_none()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event

@router.post("/{event_id}/tiers", response_model=TicketTierResponse, status_code=status.HTTP_201_CREATED)
def create_tier(event_id: int, tier_in: TicketTierCreate, db: Session = Depends(get_db)):
    # Check if event exists
    stmt = select(Event).where(Event.id == event_id)
    db_event = db.execute(stmt).scalar_one_or_none()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    db_tier = TicketTier(
        event_id=event_id,
        name=tier_in.name,
        price=tier_in.price,
        capacity=tier_in.capacity,
    )
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

@router.get("/{event_id}/tiers", response_model=List[TicketTierResponse])
def get_event_tiers(event_id: int, db: Session = Depends(get_db)):
    # Check if event exists
    stmt = select(Event).where(Event.id == event_id)
    db_event = db.execute(stmt).scalar_one_or_none()
    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    stmt_tiers = select(TicketTier).where(TicketTier.event_id == event_id)
    result = db.execute(stmt_tiers)
    return result.scalars().all()

@router.post("/{event_id}/reserve", response_model=BookingSessionResponse, status_code=status.HTTP_201_CREATED)
def reserve_tickets(event_id: int, request: BookingReservationRequest, db: Session = Depends(get_db)):
    try:
        # Check if event exists first
        event_stmt = select(Event).where(Event.id == event_id)
        db_event = db.execute(event_stmt).scalar_one_or_none()
        if not db_event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

        # 1. Fetch TicketTier with .with_for_update() lock.
        tier_stmt = select(TicketTier).where(TicketTier.id == request.tier_id).with_for_update()
        tier = db.execute(tier_stmt).scalar_one_or_none()
        
        if not tier:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket tier not found")
            
        if tier.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Ticket tier does not belong to this event"
            )
            
        if not tier.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sales for this ticket tier are paused"
            )
            
        now = datetime.now()
        if tier.sales_start_at and now < tier.sales_start_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sales for this ticket tier have not started yet"
            )
            
        if tier.sales_end_at and now > tier.sales_end_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sales for this ticket tier have ended"
            )
            
        # 2. Query BookingSession to sum up active quantities for the tier_id
        active_reservations_stmt = select(func.sum(BookingSession.quantity)).where(
            BookingSession.tier_id == request.tier_id,
            or_(
                BookingSession.status == "paid",
                and_(
                    BookingSession.status == "reserved",
                    BookingSession.expires_at > now
                )
            )
        )
        active_reservations_sum = db.execute(active_reservations_stmt).scalar() or 0
        
        # 3. Check capacity
        if active_reservations_sum + request.quantity > tier.capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient ticket capacity available"
            )
            
        # 4. Otherwise, create BookingSession and pre-allocate Ticket rows in "reserved" status.
        booking_id = str(uuid.uuid4())
        expires_at = now + timedelta(minutes=10)
        
        booking_session = BookingSession(
            id=booking_id,
            tier_id=request.tier_id,
            quantity=request.quantity,
            status="reserved",
            created_at=now,
            expires_at=expires_at,
            stripe_session_id=None
        )
        db.add(booking_session)
        
        for _ in range(request.quantity):
            ticket = Ticket(
                booking_session_id=booking_id,
                tier_id=request.tier_id,
                ticket_code=generate_unique_ticket_code(db),
                status="reserved"
            )
            db.add(ticket)
            
        db.commit()
        db.refresh(booking_session)
        return booking_session
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction error: {str(e)}"
        )
