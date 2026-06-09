import os
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.backend.database import get_db
from src.backend.models import Event, SystemSetting, TicketTier, Ticket

router = APIRouter(prefix="/admin", tags=["admin"])

from src.backend.i18n import get_translator

templates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_path)
templates.env.globals["hasattr"] = hasattr

original_template_response = templates.TemplateResponse
def custom_template_response(request: Request, name: str, context: dict, *args, **kwargs):
    context["_"] = get_translator(request)
    return original_template_response(request=request, name=name, context=context, *args, **kwargs)
templates.TemplateResponse = custom_template_response

# ----------------- AUTHENTICATION DEPENDENCY -----------------
def get_admin_user(request: Request, session_token: Optional[str] = Cookie(None)):
    expected_token = "admin_session"
    if session_token != expected_token:
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Unauthorized")
        raise HTTPException(
            status_code=303,
            detail="Redirect to login",
            headers={"Location": "/admin/login"}
        )
    return "admin"

# ----------------- BRANDING HELPER -----------------
def get_branding(db: Session):
    site_name = db.execute(select(SystemSetting).where(SystemSetting.key == "site_name")).scalar_one_or_none()
    site_logo = db.execute(select(SystemSetting).where(SystemSetting.key == "site_logo")).scalar_one_or_none()
    primary_color = db.execute(select(SystemSetting).where(SystemSetting.key == "primary_color")).scalar_one_or_none()
    accent_color = db.execute(select(SystemSetting).where(SystemSetting.key == "accent_color")).scalar_one_or_none()
    currency = db.execute(select(SystemSetting).where(SystemSetting.key == "currency")).scalar_one_or_none()
    ticket_code_type = db.execute(select(SystemSetting).where(SystemSetting.key == "ticket_code_type")).scalar_one_or_none()
    delivery_cost = db.execute(select(SystemSetting).where(SystemSetting.key == "delivery_cost")).scalar_one_or_none()
    
    return {
        "site_name": site_name.value if site_name else "OpenTicket",
        "site_logo": site_logo.value if site_logo else "/static/logo.png",
        "primary_color": primary_color.value if primary_color else "#ffffff",
        "accent_color": accent_color.value if accent_color else "#ff0055",
        "currency": currency.value if currency else "USD",
        "ticket_code_type": ticket_code_type.value if ticket_code_type else "alphanumeric_8",
        "delivery_cost": float(delivery_cost.value) if delivery_cost else 0.0,
    }

# ----------------- AUTH ROUTING -----------------
@router.get("/login", response_class=HTMLResponse)
def admin_login_get(request: Request, db: Session = Depends(get_db)):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context=branding
    )

@router.post("/login")
def admin_login_post(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    expected_password = os.getenv("ADMIN_PASSWORD", "admin123")
    if password == expected_password:
        response = RedirectResponse(url="/admin/events", status_code=303)
        response.set_cookie(
            key="session_token",
            value="admin_session",
            path="/",
            httponly=True,
            samesite="lax"
        )
        return response
    else:
        branding = get_branding(db)
        return templates.TemplateResponse(
            request=request,
            name="admin_login.html",
            context={
                "error_message": "Invalid password",
                **branding
            }
        )

@router.get("/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("session_token", path="/")
    return response

# ----------------- SECURED ROUTING -----------------
@router.get("", response_class=HTMLResponse)
@router.get("/events", response_class=HTMLResponse)
def admin_dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    admin: str = Depends(get_admin_user)
):
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
def admin_create_event_form(
    request: Request, 
    db: Session = Depends(get_db), 
    admin: str = Depends(get_admin_user)
):
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_new_event.html",
        context=branding
    )

@router.get("/branding", response_class=HTMLResponse)
def admin_branding_get(
    request: Request, 
    db: Session = Depends(get_db), 
    admin: str = Depends(get_admin_user)
):
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
    currency: str = Form("USD"),
    ticket_code_type: str = Form("alphanumeric_8"),
    delivery_cost: float = Form(0.0),
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    for key, val in [
        ("site_name", site_name),
        ("site_logo", site_logo),
        ("primary_color", primary_color),
        ("accent_color", accent_color),
        ("currency", currency.upper()),
        ("ticket_code_type", ticket_code_type),
        ("delivery_cost", str(delivery_cost))
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

@router.get("/events/{event_id}", response_class=HTMLResponse)
def admin_event_detail(
    request: Request,
    event_id: int,
    checkin_status: str = None,
    checkin_message: str = None,
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    stmt = select(Event).where(Event.id == event_id)
    event = db.execute(stmt).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    branding = get_branding(db)
    
    # Calculate statistics
    tickets_stmt = select(Ticket).join(TicketTier).where(TicketTier.event_id == event_id)
    all_active_tickets = db.execute(tickets_stmt).scalars().all()
    
    total_sold = len(all_active_tickets)
    total_paid_tickets = len([t for t in all_active_tickets if t.status in ("valid", "checked_in")])
    total_checked_in = len([t for t in all_active_tickets if t.status == "checked_in"])
    total_revenue = sum(t.tier.price for t in all_active_tickets if t.status in ("valid", "checked_in"))
    
    total_capacity = sum(tier.capacity for tier in event.tiers)
    
    sold_pct = int((total_sold / total_capacity) * 100) if total_capacity > 0 else 0
    checkin_pct = int((total_checked_in / total_paid_tickets) * 100) if total_paid_tickets > 0 else 0
    
    return templates.TemplateResponse(
        request=request,
        name="admin_event_detail.html",
        context={
            "event": event,
            "hasattr": hasattr,
            "checkin_status": checkin_status,
            "checkin_message": checkin_message,
            "total_sold": total_sold,
            "total_capacity": total_capacity,
            "total_paid_tickets": total_paid_tickets,
            "total_checked_in": total_checked_in,
            "total_revenue": total_revenue,
            "sold_pct": sold_pct,
            "checkin_pct": checkin_pct,
            **branding
        }
    )

@router.post("/events/new")
def admin_create_event(
    name: str = Form(...),
    description: str = Form(""),
    date: str = Form(...),
    location: str = Form(...),
    visible_from: Optional[str] = Form(None),
    offers_physical_tickets: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    try:
        event_date = datetime.fromisoformat(date)
    except Exception:
        event_date = datetime.now()
        
    visible_dt = None
    if visible_from:
        try:
            visible_dt = datetime.fromisoformat(visible_from)
        except Exception:
            pass
            
    db_event = Event(
        name=name,
        description=description,
        date=event_date,
        location=location,
        visible_from=visible_dt,
        offers_physical_tickets=(offers_physical_tickets == "true")
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
    sales_start_at: Optional[str] = Form(None),
    sales_end_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    event_stmt = select(Event).where(Event.id == event_id)
    event = db.execute(event_stmt).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    start_dt = None
    if sales_start_at:
        try:
            start_dt = datetime.fromisoformat(sales_start_at)
        except Exception:
            pass
            
    end_dt = None
    if sales_end_at:
        try:
            end_dt = datetime.fromisoformat(sales_end_at)
        except Exception:
            pass
            
    db_tier = TicketTier(
        event_id=event_id,
        name=name,
        price=price,
        capacity=capacity,
        is_active=True,
        sales_start_at=start_dt,
        sales_end_at=end_dt
    )
    db.add(db_tier)
    db.commit()
    return RedirectResponse(url=f"/admin/events/{event_id}", status_code=303)

@router.post("/events/{event_id}/checkin", response_class=HTMLResponse)
def admin_checkin_ticket(
    request: Request,
    event_id: int,
    ticket_code: str = Form(...),
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
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
            
    # Recalculate stats
    tickets_stmt = select(Ticket).join(TicketTier).where(TicketTier.event_id == event_id)
    all_active_tickets = db.execute(tickets_stmt).scalars().all()
    
    total_sold = len(all_active_tickets)
    total_paid_tickets = len([t for t in all_active_tickets if t.status in ("valid", "checked_in")])
    total_checked_in = len([t for t in all_active_tickets if t.status == "checked_in"])
    total_revenue = sum(t.tier.price for t in all_active_tickets if t.status in ("valid", "checked_in"))
    total_capacity = sum(tier.capacity for tier in event.tiers)
    sold_pct = int((total_sold / total_capacity) * 100) if total_capacity > 0 else 0
    checkin_pct = int((total_checked_in / total_paid_tickets) * 100) if total_paid_tickets > 0 else 0
            
    return templates.TemplateResponse(
        request=request,
        name="admin_event_detail.html",
        context={
            "event": event,
            "hasattr": hasattr,
            "checkin_status": checkin_status,
            "checkin_message": checkin_message,
            "total_sold": total_sold,
            "total_capacity": total_capacity,
            "total_paid_tickets": total_paid_tickets,
            "total_checked_in": total_checked_in,
            "total_revenue": total_revenue,
            "sold_pct": sold_pct,
            "checkin_pct": checkin_pct,
            **branding
        }
    )

# ----------------- TICKET TIER EDITING/DELETION -----------------
@router.get("/events/{event_id}/tiers/{tier_id}/edit", response_class=HTMLResponse)
def admin_tier_edit_get(
    request: Request,
    event_id: int,
    tier_id: int,
    error_message: str = None,
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    stmt = select(TicketTier).where(TicketTier.id == tier_id)
    tier = db.execute(stmt).scalar_one_or_none()
    if not tier or tier.event_id != event_id:
        raise HTTPException(status_code=404, detail="Ticket tier not found")
        
    branding = get_branding(db)
    return templates.TemplateResponse(
        request=request,
        name="admin_tier_edit.html",
        context={
            "event_id": event_id,
            "tier": tier,
            "error_message": error_message,
            "hasattr": hasattr,
            **branding
        }
    )

@router.post("/events/{event_id}/tiers/{tier_id}/edit")
def admin_tier_edit_post(
    request: Request,
    event_id: int,
    tier_id: int,
    name: str = Form(...),
    price: float = Form(...),
    capacity: int = Form(...),
    is_active: Optional[bool] = Form(False),
    sales_start_at: Optional[str] = Form(None),
    sales_end_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    stmt = select(TicketTier).where(TicketTier.id == tier_id)
    tier = db.execute(stmt).scalar_one_or_none()
    if not tier or tier.event_id != event_id:
        raise HTTPException(status_code=404, detail="Ticket tier not found")
        
    # Verify capacity can be edited (must be >= sold tickets to prevent negative space)
    tickets_stmt = select(Ticket).where(Ticket.tier_id == tier_id)
    active_tickets_count = len(db.execute(tickets_stmt).scalars().all())
    if capacity < active_tickets_count:
        branding = get_branding(db)
        return templates.TemplateResponse(
            request=request,
            name="admin_tier_edit.html",
            context={
                "event_id": event_id,
                "tier": tier,
                "error_message": f"Cannot reduce capacity to {capacity}. Already sold {active_tickets_count} tickets.",
                "hasattr": hasattr,
                **branding
            }
        )
        
    start_dt = None
    if sales_start_at:
        try:
            start_dt = datetime.fromisoformat(sales_start_at)
        except Exception:
            pass
            
    end_dt = None
    if sales_end_at:
        try:
            end_dt = datetime.fromisoformat(sales_end_at)
        except Exception:
            pass
            
    tier.name = name
    tier.price = price
    tier.capacity = capacity
    tier.is_active = is_active
    tier.sales_start_at = start_dt
    tier.sales_end_at = end_dt
    db.commit()
    
    return RedirectResponse(url=f"/admin/events/{event_id}", status_code=303)

@router.post("/events/{event_id}/tiers/{tier_id}/delete")
def admin_tier_delete(
    request: Request,
    event_id: int,
    tier_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(get_admin_user)
):
    stmt = select(TicketTier).where(TicketTier.id == tier_id)
    tier = db.execute(stmt).scalar_one_or_none()
    if not tier or tier.event_id != event_id:
        raise HTTPException(status_code=404, detail="Ticket tier not found")
        
    # Check if tickets have been sold
    tickets_stmt = select(Ticket).where(Ticket.tier_id == tier_id, Ticket.status.in_(("valid", "checked_in")))
    sold_tickets = db.execute(tickets_stmt).scalars().all()
    if len(sold_tickets) > 0:
        # Redirect back to edit page with error message
        branding = get_branding(db)
        return templates.TemplateResponse(
            request=request,
            name="admin_tier_edit.html",
            context={
                "event_id": event_id,
                "tier": tier,
                "error_message": "Cannot delete tier because tickets have already been sold. Please pause sales instead.",
                "hasattr": hasattr,
                **branding
            }
        )
        
    db.delete(tier)
    db.commit()
    return RedirectResponse(url=f"/admin/events/{event_id}", status_code=303)
