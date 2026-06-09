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

# Create database tables
Base.metadata.create_all(bind=engine)

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

templates_path = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_path)
templates.env.globals["hasattr"] = hasattr

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html", # Default to admin dashboard if visited directly
        context={
            "request": request,
            "events": [],
            **branding
        }
    )

@app.get("/success", response_class=HTMLResponse)
def payment_success(request: Request, session_id: str, db: Session = Depends(get_db)):
    stripe.api_key = os.getenv("STRIPE_API_KEY", "sk_test_mock")
    branding = get_branding(db)
    
    try:
        # Retrieve Stripe session
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


