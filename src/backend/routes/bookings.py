import os
import uuid
import stripe
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session

from src.backend.database import get_db
from src.backend.models import BookingSession, Ticket, TicketTier

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

stripe.api_key = os.getenv("STRIPE_API_KEY", "sk_test_mock")

@router.post("/cleanup", status_code=status.HTTP_200_OK)
def cleanup_expired_reservations(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Find all booking sessions in "reserved" state that have expired
    stmt = select(BookingSession).where(
        BookingSession.status == "reserved",
        BookingSession.expires_at < now
    )
    expired_bookings = db.execute(stmt).scalars().all()
    
    for booking in expired_bookings:
        booking.status = "expired"
        # Delete the associated tickets to release/reclaim capacity
        booking.tickets.clear()
        
    db.commit()
    return {"status": "success", "cleaned_count": len(expired_bookings)}

@router.post("/{booking_session_id}/checkout")
def create_checkout_session(booking_session_id: str, request: Request, db: Session = Depends(get_db)):
    stmt = select(BookingSession).where(BookingSession.id == booking_session_id)
    booking = db.execute(stmt).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking session not found")
    
    if booking.status == "paid":
        raise HTTPException(status_code=400, detail="Booking already paid")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if booking.expires_at <= now or booking.status == "expired" or booking.status == "cancelled":
        if booking.status == "reserved" and booking.expires_at <= now:
            booking.status = "expired"
            booking.tickets.clear()
            db.commit()
        raise HTTPException(status_code=400, detail="Booking session has expired or is cancelled")
    
    tier_stmt = select(TicketTier).where(TicketTier.id == booking.tier_id)
    tier = db.execute(tier_stmt).scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Ticket tier not found")
        
    try:
        base_url = str(request.base_url).rstrip("/")
        success_url = f"{base_url}/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/cancel"
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f"Tickets for {tier.name}",
                    },
                    'unit_amount': int(tier.price * 100),
                },
                'quantity': booking.quantity,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=booking.id,
        )
        booking.stripe_session_id = session.id
        db.commit()
        return {"checkout_url": session.url, "url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock_secret")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {str(e)}")
        
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        booking_id = getattr(session, "client_reference_id", None)
        if not booking_id:
            raise HTTPException(status_code=400, detail="Missing client_reference_id in session")
            
        stmt = select(BookingSession).where(BookingSession.id == booking_id)
        booking = db.execute(stmt).scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking session not found")
            
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if booking.expires_at <= now or booking.status == "expired":
            # Acquire row-level lock on the TicketTier
            tier_stmt = select(TicketTier).where(TicketTier.id == booking.tier_id).with_for_update()
            tier = db.execute(tier_stmt).scalar_one_or_none()
            if not tier:
                raise HTTPException(status_code=404, detail="Ticket tier not found")
                
            # Compute current active reservations on the tier (excluding this booking)
            active_reservations_stmt = select(func.sum(BookingSession.quantity)).where(
                BookingSession.tier_id == booking.tier_id,
                BookingSession.id != booking.id,
                or_(
                    BookingSession.status == "paid",
                    and_(
                        BookingSession.status == "reserved",
                        BookingSession.expires_at > now
                    )
                )
            )
            active_reservations_sum = db.execute(active_reservations_stmt).scalar() or 0
            
            if active_reservations_sum + booking.quantity <= tier.capacity:
                booking.status = "paid"
                # If tickets were cleared/deleted when the booking expired, recreate them
                tickets_stmt = select(Ticket).where(Ticket.booking_session_id == booking_id)
                tickets = db.execute(tickets_stmt).scalars().all()
                if len(tickets) < booking.quantity:
                    for _ in range(booking.quantity - len(tickets)):
                        ticket = Ticket(
                            booking_session_id=booking.id,
                            tier_id=booking.tier_id,
                            ticket_code=uuid.uuid4().hex,
                            status="valid"
                        )
                        db.add(ticket)
                else:
                    for ticket in tickets:
                        ticket.status = "valid"
            else:
                booking.status = "failed"
                tickets_stmt = select(Ticket).where(Ticket.booking_session_id == booking_id)
                tickets = db.execute(tickets_stmt).scalars().all()
                for ticket in tickets:
                    ticket.status = "cancelled"
                    
                # Attempt to trigger Stripe refund if payment_intent is present
                payment_intent = getattr(session, "payment_intent", None)
                if payment_intent:
                    try:
                        stripe.Refund.create(payment_intent=payment_intent)
                    except Exception as refund_err:
                        print(f"Stripe refund failed: {refund_err}")
        else:
            booking.status = "paid"
            # Mark all tickets for this booking as valid
            tickets_stmt = select(Ticket).where(Ticket.booking_session_id == booking_id)
            tickets = db.execute(tickets_stmt).scalars().all()
            for ticket in tickets:
                ticket.status = "valid"
            
        db.commit()
        return {"status": "success"}
        
    return {"status": "ignored"}
