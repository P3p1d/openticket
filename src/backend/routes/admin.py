import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.database import get_db
from src.backend.models import Event, SystemSetting

router = APIRouter(prefix="/admin", tags=["admin"])

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)
templates.env.globals["hasattr"] = hasattr

def get_branding(db: Session):
    site_name = db.execute(select(SystemSetting).where(SystemSetting.key == "site_name")).scalar_one_or_none()
    site_logo = db.execute(select(SystemSetting).where(SystemSetting.key == "site_logo")).scalar_one_or_none()
    primary_color = db.execute(select(SystemSetting).where(SystemSetting.key == "primary_color")).scalar_one_or_none()
    accent_color = db.execute(select(SystemSetting).where(SystemSetting.key == "accent_color")).scalar_one_or_none()
    
    return {
        "site_name": site_name.value if site_name else "OpenTicket",
        "site_logo": site_logo.value if site_logo else "/static/logo.png",
        "primary_color": primary_color.value if primary_color else "#ffffff",
        "accent_color": accent_color.value if accent_color else "#ff0055",
    }

@router.get("", response_class=HTMLResponse)
@router.get("/events", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    events = db.execute(select(Event)).scalars().all()
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "events": events,
            **branding
        }
    )

@router.get("/events/new", response_class=HTMLResponse)
def admin_create_event_form(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_new_event.html",
        context=branding
    )

@router.get("/branding", response_class=HTMLResponse)
def admin_branding_get(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_branding.html",
        context=branding
    )

@router.post("/branding")
def admin_branding_post(
    request: Request,
    site_name: str = Form(...),
    site_logo: str = Form(...),
    primary_color: str = Form(...),
    accent_color: str = Form(...),
    db: Session = Depends(get_db)
):
    for key, val in [
        ("site_name", site_name),
        ("site_logo", site_logo),
        ("primary_color", primary_color),
        ("accent_color", accent_color)
    ]:
        setting = db.execute(select(SystemSetting).where(SystemSetting.key == key)).scalar_one_or_none()
        if not setting:
            setting = SystemSetting(key=key, value=val)
            db.add(setting)
        else:
            setting.value = val
    db.commit()
    
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_branding.html",
        context=branding
    )


from fastapi.responses import RedirectResponse
from src.backend.models import TicketTier, Ticket
from datetime import datetime

@router.get("/events/{event_id}", response_class=HTMLResponse)
def admin_event_detail(
    request: Request,
    event_id: int,
    checkin_status: str = None,
    checkin_message: str = None,
    db: Session = Depends(get_db)
):
    stmt = select(Event).where(Event.id == event_id)
    event = db.execute(stmt).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_event_detail.html",
        context={
            "event": event,
            "hasattr": hasattr,
            "checkin_status": checkin_status,
            "checkin_message": checkin_message,
            **branding
        }
    )

@router.post("/events/new")
def admin_create_event(
    name: str = Form(...),
    description: str = Form(""),
    date: str = Form(...),
    location: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        event_date = datetime.fromisoformat(date)
    except Exception:
        event_date = datetime.now()
        
    db_event = Event(
        name=name,
        description=description,
        date=event_date,
        location=location
    )
    db.add(db_event)
    db.commit()
    return RedirectResponse(url="/admin/events", status_code=303)

@router.post("/events/{event_id}/tiers")
def admin_add_tier(
    event_id: int,
    name: str = Form(...),
    price: float = Form(...),
    capacity: int = Form(...),
    db: Session = Depends(get_db)
):
    event_stmt = select(Event).where(Event.id == event_id)
    event = db.execute(event_stmt).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    db_tier = TicketTier(
        event_id=event_id,
        name=name,
        price=price,
        capacity=capacity
    )
    db.add(db_tier)
    db.commit()
    return RedirectResponse(url=f"/admin/events/{event_id}", status_code=303)

@router.post("/events/{event_id}/checkin", response_class=HTMLResponse)
def admin_checkin_ticket(
    request: Request,
    event_id: int,
    ticket_code: str = Form(...),
    db: Session = Depends(get_db)
):
    ticket_stmt = select(Ticket).where(Ticket.ticket_code == ticket_code.strip())
    ticket = db.execute(ticket_stmt).scalar_one_or_none()
    
    branding = get_branding(db)
    event_stmt = select(Event).where(Event.id == event_id)
    event = db.execute(event_stmt).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    if not ticket:
        checkin_status = "error"
        checkin_message = "TICKET INVALID: Code not found in system."
    else:
        tier_stmt = select(TicketTier).where(TicketTier.id == ticket.tier_id)
        tier = db.execute(tier_stmt).scalar_one_or_none()
        if not tier or tier.event_id != event_id:
            checkin_status = "error"
            checkin_message = f"TICKET INVALID: Ticket does not belong to event '{event.name}'."
        elif ticket.status == "checked_in":
            checkin_status = "error"
            checkin_message = "ALREADY CHECKED IN: This ticket was already validated."
        elif ticket.status == "valid":
            ticket.status = "checked_in"
            db.commit()
            checkin_status = "success"
            checkin_message = f"CHECK-IN SUCCESSFUL: Valid {tier.name} ticket checked in!"
        else:
            checkin_status = "error"
            checkin_message = f"TICKET INVALID: Status is '{ticket.status}'."
            
    return templates.TemplateResponse(
        request=request,
        name="admin_event_detail.html",
        context={
            "event": event,
            "hasattr": hasattr,
            "checkin_status": checkin_status,
            "checkin_message": checkin_message,
            **branding
        }
    )

