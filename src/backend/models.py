from datetime import datetime
from typing import Optional, List
from sqlalchemy import ForeignKey, String, DateTime, Float, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    
    # relationships
    tiers: Mapped[List["TicketTier"]] = relationship(
        "TicketTier", 
        back_populates="event", 
        cascade="all, delete-orphan"
    )

class TicketTier(Base):
    __tablename__ = "ticket_tiers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # relationships
    event: Mapped["Event"] = relationship("Event", back_populates="tiers")
    booking_sessions: Mapped[List["BookingSession"]] = relationship(
        "BookingSession", 
        back_populates="tier", 
        cascade="all, delete-orphan"
    )
    tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket", 
        back_populates="tier", 
        cascade="all, delete-orphan"
    )

class BookingSession(Base):
    __tablename__ = "booking_sessions"
    
    id: Mapped[str] = mapped_column(String, primary_key=True) # UUID string representation
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="reserved", nullable=False) # "reserved", "paid", "expired", "cancelled"
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False) # UTC datetime
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False) # created_at + reservation window
    stripe_session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # relationships
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="booking_sessions")
    tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket", 
        back_populates="booking_session", 
        cascade="all, delete-orphan"
    )

    @property
    def booking_session_id(self) -> str:
        return self.id

class Ticket(Base):
    __tablename__ = "tickets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    booking_session_id: Mapped[str] = mapped_column(
        String, 
        ForeignKey("booking_sessions.id", ondelete="CASCADE"), 
        nullable=False
    )
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("ticket_tiers.id", ondelete="CASCADE"), nullable=False)
    ticket_code: Mapped[str] = mapped_column(String, unique=True, nullable=False) # unique hex UUID
    status: Mapped[str] = mapped_column(String, default="reserved", nullable=False) # "reserved", "valid", "checked_in", "refunded"
    
    # relationships
    booking_session: Mapped["BookingSession"] = relationship("BookingSession", back_populates="tickets")
    tier: Mapped["TicketTier"] = relationship("TicketTier", back_populates="tickets")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)

