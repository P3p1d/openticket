# Handoff Report — Challenger 1 for Milestone 1

## 1. Observation

1. **Uvicorn Concurrency Test Setup**:
   `tests/test_concurrency.py` sets up a module-scoped server:
   ```python
   # Start uvicorn server in a background thread
   config = uvicorn.Config(app, host="127.0.0.1", port=8012, log_level="warning")
   server = uvicorn.Server(config)
   thread = threading.Thread(target=server.run)
   thread.daemon = True
   thread.start()
   ```
2. **SQLite Transaction Locking Listener**:
   In `src/backend/database.py`, lines 36-38 configures the following engine listener for SQLite:
   ```python
   @event.listens_for(engine, "begin")
   def do_begin(conn):
       conn.exec_driver_sql("BEGIN IMMEDIATE")
   ```
3. **Active Reservations Query Logic**:
   In `src/backend/routes/events.py`, lines 97-107 calculates active reservations using:
   ```python
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
   ```
4. **Stripe Webhook Handler**:
   In `src/backend/routes/bookings.py`, lines 70-89 processes the successful checkout event:
   ```python
   if event["type"] == "checkout.session.completed":
       session = event["data"]["object"]
       booking_id = session.get("client_reference_id")
       ...
       stmt = select(BookingSession).where(BookingSession.id == booking_id)
       booking = db.execute(stmt).scalar_one_or_none()
       ...
       booking.status = "paid"
       
       # Mark all tickets for this booking as valid
       tickets_stmt = select(Ticket).where(Ticket.booking_session_id == booking_id)
       tickets = db.execute(tickets_stmt).scalars().all()
       for ticket in tickets:
           ticket.status = "valid"
           
       db.commit()
   ```
5. **Command Line Execution Attempt**:
   The agent attempted to execute `pytest -v tests/test_concurrency.py` using `run_command` and received the timeout:
   ```
   Encountered error in step execution: Permission prompt for action 'command' on target 'pytest -v tests/test_concurrency.py' timed out waiting for user response.
   ```

## 2. Logic Chain

1. **Observation 1 & 2** show that the FastAPI application database queries are fully serialized in SQLite through the use of the `BEGIN IMMEDIATE` event listener hook. This forces any write transaction to acquire a database-level write lock immediately when starting.
2. Because of this database serialization, the `/reserve` endpoint executes transactions in isolation (one-by-one). Thread A's capacity check and subsequent ticket insertion must commit and release the write lock before Thread B's write transaction can even start. Therefore, standard reservation race conditions are prevented.
3. **Observation 3** shows that when counting active reservations, any reservation whose status is `"reserved"` but where `expires_at <= now` is completely omitted from the active reservations count.
4. If a reservation is omitted, its seats are freed for other requests to claim, allowing a new customer to reserve those same tickets.
5. **Observation 4** shows that when the Stripe webhook completes, the handler searches for the booking session by ID, sets its status to `"paid"`, and marks pre-allocated tickets as `"valid"`. Crucially, this code does not check if the booking session has expired, nor does it re-verify if the tier capacity has been exceeded in the meantime.
6. Therefore, an expired reservation can proceed to checkout, complete payment, and be marked as paid and valid, creating an oversold condition where the number of valid tickets exceeds the tier's capacity.

## 3. Caveats

- Due to running in a non-interactive/unattended environment, command line test execution timed out (Observation 5). Static code analysis and the design of test cases was utilized instead of live execution output.
- PostgreSQL behaviour was not tested live, but the SQL standard `with_for_update()` locking used on the `TicketTier` row should correctly serialize capacity checks per tier.

## 4. Conclusion

The booking reservation mechanism is concurrency-safe under SQLite (due to `BEGIN IMMEDIATE` transaction serialization) and PostgreSQL (due to row-level locks via `with_for_update()`). However, **capacity limit enforcement is broken** because the system allows checkout session creation and webhook payments for expired booking sessions without re-checking capacity or session validity. This allows a user to buy expired tickets that have already been re-allocated to other users.

## 5. Verification Method

To verify the vulnerability, run the newly added adversarial tests:
```bash
pytest -v tests/test_concurrency_adversarial.py
```
- Inspect `test_oversell_via_expired_reservation` to verify that when a booking is simulated as expired, a new booking is allowed, and then both booking payments succeed, resulting in total valid tickets exceeding the capacity limit.
- If the test fails with an assertion showing `len(valid_tickets) > 5` is True, then the vulnerability is present.
