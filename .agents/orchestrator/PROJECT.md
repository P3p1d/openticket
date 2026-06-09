# Project: OpenTicket

## Architecture
OpenTicket is a self-hosted ticket selling web application in Python.
- **Backend**: FastAPI web framework, SQLAlchemy ORM.
- **Database**: SQLite by default, PostgreSQL supported. Parameterized ORM queries to prevent SQL injection.
- **Concurrency Control**: Transactional ticket booking mechanism using database row-level locking (`SELECT FOR UPDATE` in SQLAlchemy) to prevent overselling.
- **Payment Gateway**: Modular adapter interface with a Stripe Checkout provider. Supports temporary ticket reservations with timeouts and webhook notifications.
- **Frontend & Admin**: Jinja2 templates, minimalist dark-theme styling, configurable custom branding.
- **Widget**: Embeddable Vanilla JavaScript & CSS purchase widget loading via `<script>`.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Requirement-driven test suite (Tiers 1-4). Outputs TEST_READY.md. | None | IN_PROGRESS |
| 1 | Backend API & Concurrency | Database schemas, SQLite/PostgreSQL, transactional booking (row-level locking). | None | IN_PROGRESS |
| 2 | Stripe Integration | Payment adapter, Stripe checkout, reservation timeouts, webhook handler. | M1 | PLANNED |
| 3 | Frontend & Admin Panel | Jinja2 templates, customizable branding, order logs, check-in view. | M1 | PLANNED |
| 4 | Embeddable Widget | Lightweight JS widget interfacing with API. | M2, M3 | PLANNED |
| 5 | Acceptance & Hardening | Phase 1: 100% E2E test pass. Phase 2: Adversarial hardening. | E2E, M4 | PLANNED |

## Interface Contracts
### Ticket Booking & Booking Session
- `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Returns `booking_session_id`, `expires_at`.
- `POST /api/bookings/{booking_session_id}/checkout`: Initiate checkout, return Stripe checkout URL.
- `POST /api/webhooks/stripe`: Stripe webhook handler. Marks booking as paid and generates ticket check-in codes.

## Code Layout
- `src/backend/`: FastAPI application code.
  - `src/backend/main.py`: App entry point.
  - `src/backend/models.py`: SQLAlchemy database models.
  - `src/backend/database.py`: DB engine and session setup.
  - `src/backend/routes/`: Router endpoints.
  - `src/backend/payment/`: Payment gateway interfaces and adapters.
  - `src/backend/templates/`: Jinja2 admin templates.
- `src/frontend/`: Static assets and embeddable widget.
  - `src/frontend/widget.js`: The embeddable widget.
- `tests/`: Automated test suite.
