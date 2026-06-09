from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from src.backend.database import engine
from src.backend.models import Base
from src.backend.routes import events
from src.backend.routes.bookings import router as bookings_router, webhook_router
from src.backend.routes.admin import router as admin_router
from src.backend.routes.widget import router as widget_router

# Database tables are now managed by Alembic
# Migrations are run on startup via docker-compose

app = FastAPI(
    title="OpenTicket API",
    description="Backend API & Concurrency Control for OpenTicket booking platform",
    version="1.0.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Register routers
app.include_router(events.router)
app.include_router(bookings_router)
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(widget_router)

# Import templates and DB access for customer views
from fastapi import Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
import stripe

from src.backend.database import get_db
from src.backend.models import BookingSession, Ticket, TicketTier, Event
from src.backend.routes.admin import get_branding
from src.backend.i18n import get_translator

templates_path = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_path)
templates.env.globals["hasattr"] = hasattr

original_template_response = templates.TemplateResponse
def custom_template_response(request: Request, name: str, context: dict, *args, **kwargs):
    context["_"] = get_translator(request)
    return original_template_response(request=request, name=name, context=context, *args, **kwargs)
templates.TemplateResponse = custom_template_response

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    stmt = select(Event).order_by(Event.date.asc())
    events = db.execute(stmt).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "events": events,
            "hasattr": hasattr,
            **branding
        }
    )

@app.get("/events/{event_id}", response_class=HTMLResponse)
def read_event(request: Request, event_id: int, db: Session = Depends(get_db)):
    branding = get_branding(db)
    # Check if event exists
    stmt = select(Event).where(Event.id == event_id)
    event = db.execute(stmt).scalar_one_or_none()
    if not event:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "request": request,
                "error_message": "Event not found",
                **branding
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="public_event_detail.html",
        context={
            "request": request,
            "event_id": event_id,
            **branding
        }
    )

from fastapi import Form
from fastapi.responses import RedirectResponse

@app.get("/checkout/{session_id}", response_class=HTMLResponse)
def checkout_form(request: Request, session_id: str, db: Session = Depends(get_db)):
    branding = get_branding(db)
    
    stmt = select(BookingSession).where(BookingSession.id == session_id)
    booking = db.execute(stmt).scalar_one_or_none()
    
    if not booking:
        return templates.TemplateResponse(request=request, name="error.html", context={"error_message": "Booking session not found", **branding})
        
    tier = db.execute(select(TicketTier).where(TicketTier.id == booking.tier_id)).scalar_one_or_none()
    event = db.execute(select(Event).where(Event.id == tier.event_id)).scalar_one_or_none()
    
    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "booking": booking,
            "tier": tier,
            "event": event,
            "hasattr": hasattr,
            **branding
        }
    )

@app.post("/checkout/{session_id}")
def process_checkout(
    request: Request,
    session_id: str,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    customer_address: str = Form(""),
    delivery_method: str = Form("digital"),
    db: Session = Depends(get_db)
):
    stmt = select(BookingSession).where(BookingSession.id == session_id)
    booking = db.execute(stmt).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking session not found")
        
    booking.customer_name = customer_name
    booking.customer_email = customer_email
    booking.customer_address = customer_address
    booking.delivery_method = delivery_method
    db.commit()
    
    # We will implement the mock payment step here, but for now just mock it directly and redirect to success
    # Since the user requested a mock paygate, we will redirect to /api/mock-paygate/{session_id}
    return RedirectResponse(url=f"/api/mock-paygate/{session_id}", status_code=303)

@app.get("/api/mock-paygate/{session_id}", response_class=HTMLResponse)
def mock_paygate_get(request: Request, session_id: str, db: Session = Depends(get_db)):
    branding = get_branding(db)
    
    stmt = select(BookingSession).where(BookingSession.id == session_id)
    booking = db.execute(stmt).scalar_one_or_none()
    
    if not booking:
        return templates.TemplateResponse(request=request, name="error.html", context={"error_message": "Booking session not found", **branding})
        
    tier = db.execute(select(TicketTier).where(TicketTier.id == booking.tier_id)).scalar_one_or_none()
    
    # Calculate total
    total_amount = tier.price * booking.quantity
    if booking.delivery_method == "physical":
        total_amount += branding.get("delivery_cost", 0.0)
        
    return templates.TemplateResponse(
        request=request,
        name="mock_paygate.html",
        context={
            "booking": booking,
            "tier": tier,
            "total_amount": total_amount,
            **branding
        }
    )

@app.post("/api/mock-paygate/{session_id}")
def mock_paygate_post(request: Request, session_id: str, db: Session = Depends(get_db)):
    stmt = select(BookingSession).where(BookingSession.id == session_id)
    booking = db.execute(stmt).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking session not found")
        
    from datetime import datetime, timezone
    from sqlalchemy import func, or_, and_
    from src.backend.routes.events import generate_unique_ticket_code
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if booking.expires_at <= now or booking.status == "expired":
        raise HTTPException(status_code=400, detail="Booking expired")
        
    # Process payment mock
    booking.status = "paid"
    
    # Mark tickets as valid
    tickets_stmt = select(Ticket).where(Ticket.booking_session_id == session_id)
    tickets = db.execute(tickets_stmt).scalars().all()
    for ticket in tickets:
        ticket.status = "valid"
        
    db.commit()
    
    return RedirectResponse(url=f"/success?session_id=mock_{session_id}", status_code=303)

@app.get("/success", response_class=HTMLResponse)
def payment_success(request: Request, session_id: str, db: Session = Depends(get_db)):
    branding = get_branding(db)
    
    try:
        if session_id.startswith("mock_"):
            booking_id = session_id.replace("mock_", "")
        else:
            # Retrieve Stripe session
            stripe.api_key = os.getenv("STRIPE_API_KEY", "sk_test_mock")
            stripe_session = stripe.checkout.Session.retrieve(session_id)
            booking_id = getattr(stripe_session, "client_reference_id", None)
            
            if not booking_id:
                raise Exception("Missing client_reference_id in Stripe session")
            
        # Retrieve Booking
        booking_stmt = select(BookingSession).where(BookingSession.id == booking_id)
        booking = db.execute(booking_stmt).scalar_one_or_none()
        
        if not booking:
            raise Exception("Booking not found")
            
        # Retrieve Tier and Event
        tier_stmt = select(TicketTier).where(TicketTier.id == booking.tier_id)
        tier = db.execute(tier_stmt).scalar_one_or_none()
        if not tier:
            raise Exception("Ticket tier not found")
            
        event_stmt = select(Event).where(Event.id == tier.event_id)
        event = db.execute(event_stmt).scalar_one_or_none()
        if not event:
            raise Exception("Event not found")
            
        # Retrieve Tickets
        tickets_stmt = select(Ticket).where(Ticket.booking_session_id == booking_id)
        tickets = db.execute(tickets_stmt).scalars().all()
        
        return templates.TemplateResponse(
            request=request,
            name="success.html",
            context={
                "event": event,
                "tier": tier,
                "booking": booking,
                "tickets": tickets,
                "hasattr": hasattr,
                **branding
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "error_message": f"Error loading tickets: {str(e)}",
                **branding
            }
        )

@app.get("/cancel", response_class=HTMLResponse)
def payment_cancel(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="cancel.html",
        context=branding
    )


