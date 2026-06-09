## 2026-06-08T22:43:22Z

You are the Worker for Milestone 1: Backend API & Concurrency Control.
Your working directory is c:\Development\openticket\.agents\worker_m1.
Read c:\Development\openticket\.agents\sub_orch_m1\synthesis.md and the files referenced there.

Your task is to implement the following files in the c:\Development\openticket workspace:
1. c:\Development\openticket\src\backend\models.py: Define SQLAlchemy 2.0 schemas for Event, TicketTier, BookingSession, and Ticket.
2. c:\Development\openticket\src\backend\database.py: Database engine and session local configuration. Implement SQLite WAL mode and BEGIN IMMEDIATE pragma / listeners, and PostgreSQL connection pool options. Also provide get_db generator dependency.
3. c:\Development\openticket\src\backend\schemas.py: Pydantic schemas for events, tiers, reservations.
4. c:\Development\openticket\src\backend\routes\events.py: FastAPI APIRouter endpoints for creating/getting events and tiers, and the transactional reserve ticket endpoint utilizing row-level locking (.with_for_update()). Ensure 100% SQL injection prevention (only ORM constructs, no raw SQL or formatting strings).
5. c:\Development\openticket\src\backend\main.py: App entry point, middleware (CORS), router registration.
6. c:\Development\openticket\tests\test_concurrency.py: Pytest suite simulating concurrent reservations via ThreadPoolExecutor.
7. Any necessary __init__.py files under src/, src/backend/, src/backend/routes/, and tests/.

After implementing, run pytest to verify all tests pass (specifically test_concurrency.py).
Verify that the tests correctly run a background uvicorn server or direct client calls and assert that capacity is not exceeded (e.g. 5 tickets available, 12 concurrent requests -> exactly 5 successes, 7 failures).

Document the commands run, output, and test results in c:\Development\openticket\.agents\worker_m1\handoff.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
