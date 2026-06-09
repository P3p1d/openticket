import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.backend.main import app
from src.backend.models import Event, TicketTier, Ticket, BookingSession, SystemSetting

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_client():
    c = TestClient(app)
    c.cookies.set("session_token", "admin_session")
    return c

@pytest.fixture
def test_event_and_tier(client):
    # 1. Create event
    event_payload = {
        "name": "Integration Test Event",
        "description": "Integration testing event.",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "location": "Warehouse 9"
    }
    event_res = client.post("/api/events", json=event_payload)
    event_id = event_res.json()["id"]

    # 2. Create tier
    tier_payload = {
        "name": "Standard Admission",
        "price": 25.0,
        "capacity": 50
    }
    tier_res = client.post(f"/api/events/{event_id}/tiers", json=tier_payload)
    tier_id = tier_res.json()["id"]

    return event_id, tier_id

def test_admin_auth_flows(client, auth_client):
    # 1. Unauthenticated request to secure page redirects to login
    response = client.get("/admin/events", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"

    # 2. POST login with invalid password fails
    login_fail = client.post("/admin/login", data={"password": "wrong_password"}, follow_redirects=False)
    assert login_fail.status_code == 200
    assert "Invalid password" in login_fail.text

    # 3. POST login with correct password succeeds and sets session cookie
    login_success = client.post("/admin/login", data={"password": "admin123"}, follow_redirects=False)
    assert login_success.status_code == 303
    assert login_success.headers["location"] == "/admin/events"
    assert "session_token" in login_success.cookies
    assert login_success.cookies["session_token"] == "admin_session"

    # 4. Logout redirects and clears cookie
    logout_res = auth_client.get("/admin/logout", follow_redirects=False)
    assert logout_res.status_code == 303
    assert logout_res.headers["location"] == "/admin/login"

def test_tier_editing_and_deletion_safety(auth_client, db_session, test_event_and_tier):
    event_id, tier_id = test_event_and_tier

    # 1. Edit the tier via POST form
    edit_payload = {
        "name": "Updated Tier Name",
        "price": 30.0,
        "capacity": 100,
        "is_active": "on",  # HTML checkbox value "on" maps to True
        "sales_start_at": "",
        "sales_end_at": ""
    }
    edit_res = auth_client.post(
        f"/admin/events/{event_id}/tiers/{tier_id}/edit",
        data=edit_payload,
        follow_redirects=False
    )
    assert edit_res.status_code == 303
    assert edit_res.headers["location"] == f"/admin/events/{event_id}"

    db_session.expire_all()
    tier = db_session.get(TicketTier, tier_id)
    assert tier is not None
    assert tier.name == "Updated Tier Name"
    assert tier.price == 30.0
    assert tier.capacity == 100
    assert tier.is_active is True

    # 2. Simulate a sold ticket in this tier
    booking = BookingSession(
        id="book_e2e_123",
        tier_id=tier_id,
        quantity=1,
        status="paid",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None)
    )
    ticket = Ticket(
        booking_session_id="book_e2e_123",
        tier_id=tier_id,
        ticket_code="E2ETICKET123",
        status="valid"
    )
    db_session.add(booking)
    db_session.add(ticket)
    db_session.commit()

    # 3. Attempt to delete the tier (should be blocked)
    delete_res = auth_client.post(
        f"/admin/events/{event_id}/tiers/{tier_id}/delete",
        follow_redirects=False
    )
    # Renders the edit page with error message
    assert delete_res.status_code == 200
    assert "Cannot delete tier because tickets have already been sold" in delete_res.text

    # Verify tier is still in DB
    db_session.expire_all()
    assert db_session.get(TicketTier, tier_id) is not None

    # 4. Clean up ticket and booking, then delete should work
    db_session.delete(ticket)
    db_session.delete(booking)
    db_session.commit()

    delete_success_res = auth_client.post(
        f"/admin/events/{event_id}/tiers/{tier_id}/delete",
        follow_redirects=False
    )
    assert delete_success_res.status_code == 303
    assert delete_success_res.headers["location"] == f"/admin/events/{event_id}"

    db_session.expire_all()
    assert db_session.get(TicketTier, tier_id) is None

def test_sales_launch_dates_and_pausing(client, db_session, test_event_and_tier):
    event_id, tier_id = test_event_and_tier

    # 1. Sales start at in future
    db_session.expire_all()
    tier = db_session.get(TicketTier, tier_id)
    tier.sales_start_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    db_session.commit()

    res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    assert res.status_code == 400
    assert "have not started yet" in res.json()["detail"]

    # 2. Sales ended in past
    tier.sales_start_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    tier.sales_end_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    db_session.commit()

    res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    assert res.status_code == 400
    assert "have ended" in res.json()["detail"]

    # 3. Sales paused (is_active = False)
    tier.sales_start_at = None
    tier.sales_end_at = None
    tier.is_active = False
    db_session.commit()

    res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    assert res.status_code == 400
    assert "are paused" in res.json()["detail"]

def test_configurable_currencies(client, db_session, mock_stripe_checkout, test_event_and_tier):
    event_id, tier_id = test_event_and_tier

    # Set currency to EUR
    currency_setting = db_session.execute(
        select(SystemSetting).where(SystemSetting.key == "currency")
    ).scalar_one_or_none()
    if not currency_setting:
        currency_setting = SystemSetting(key="currency", value="EUR")
        db_session.add(currency_setting)
    else:
        currency_setting.value = "EUR"
    db_session.commit()

    # Reserve ticket
    reserve_res = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    booking_id = reserve_res.json()["id"]

    # Checkout
    checkout_res = client.post(f"/api/bookings/{booking_id}/checkout")
    assert checkout_res.status_code == 200

    # Verify stripe checkout session call kwargs
    assert mock_stripe_checkout.called
    kwargs = mock_stripe_checkout.call_args[1]
    assert kwargs["line_items"][0]["price_data"]["currency"] == "eur"

def test_configurable_ticket_codes(client, db_session, test_event_and_tier):
    event_id, tier_id = test_event_and_tier

    # 1. Alphanumeric 8
    code_setting = db_session.execute(
        select(SystemSetting).where(SystemSetting.key == "ticket_code_type")
    ).scalar_one_or_none()
    if not code_setting:
        code_setting = SystemSetting(key="ticket_code_type", value="alphanumeric_8")
        db_session.add(code_setting)
    else:
        code_setting.value = "alphanumeric_8"
    db_session.commit()

    res_alpha = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    booking_id_alpha = res_alpha.json()["id"]

    tickets_alpha = db_session.execute(
        select(Ticket).where(Ticket.booking_session_id == booking_id_alpha)
    ).scalars().all()
    assert len(tickets_alpha) == 1
    code_alpha = tickets_alpha[0].ticket_code
    assert len(code_alpha) == 8
    assert code_alpha.isalnum()
    assert code_alpha.isupper()

    # 2. Numeric 6
    code_setting.value = "numeric_6"
    db_session.commit()

    res_num = client.post(
        f"/api/events/{event_id}/reserve",
        json={"tier_id": tier_id, "quantity": 1}
    )
    booking_id_num = res_num.json()["id"]

    tickets_num = db_session.execute(
        select(Ticket).where(Ticket.booking_session_id == booking_id_num)
    ).scalars().all()
    assert len(tickets_num) == 1
    code_num = tickets_num[0].ticket_code
    assert len(code_num) == 6
    assert code_num.isdigit()
