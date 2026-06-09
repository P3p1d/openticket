from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Ticket Schemas
class TicketResponse(BaseModel):
    id: int
    booking_session_id: str
    tier_id: int
    ticket_code: str
    status: str

    model_config = ConfigDict(from_attributes=True)

# Booking Session Schemas
class BookingReservationRequest(BaseModel):
    tier_id: int
    quantity: int = Field(..., gt=0, description="Quantity of tickets to reserve")

class BookingSessionResponse(BaseModel):
    id: str
    booking_session_id: str
    tier_id: int
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime
    stripe_session_id: Optional[str] = None
    tickets: List[TicketResponse] = []

    model_config = ConfigDict(from_attributes=True)

# TicketTier Schemas
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

    model_config = ConfigDict(from_attributes=True)

# Event Schemas
class EventCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    date: datetime
    location: str

    @field_validator("date")
    @classmethod
    def date_must_be_in_future(cls, v: datetime) -> datetime:
        now = datetime.now(v.tzinfo) if v.tzinfo is not None else datetime.now()
        if v < now:
            raise ValueError("Event date must be in the future")
        return v


class EventResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    date: datetime
    location: str
    tiers: List[TicketTierResponse] = []

    model_config = ConfigDict(from_attributes=True)
