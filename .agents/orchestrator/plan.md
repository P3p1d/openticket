# Project Plan: OpenTicket

## Architecture & Design
OpenTicket will be built as a Python FastAPI application. It uses a SQLite database by default, with PostgreSQL supported, managed via SQLAlchemy ORM. Concurrency protection uses row-level database locking (`SELECT FOR UPDATE` or equivalent) to prevent double-selling/overselling.

## Dual-Track Strategy
We will execute two parallel tracks:
1. **E2E Testing Track**: Responsible for writing a comprehensive, opaque-box, requirement-driven test suite (Tiers 1-4). Outputs `TEST_READY.md`.
2. **Implementation Track**: Responsible for developing the system features through a sequence of milestones. The final milestone requires passing all tests and undergoing adversarial hardening.

## Milestones

### Milestone 0: Initialization & Test Infrastructure (E2E Track)
- Task: Set up the test suite structure, test runner, mock Stripe webhook framework, and Category-Partition-based test definitions.
- Output: `TEST_INFRA.md`, skeleton E2E tests covering Tiers 1-4.

### Milestone 1: Database, API Scaffolding & Concurrency Control (Implementation Track)
- Task: Database models (events, tiers, orders, tickets), migration/seeding, FastAPI application setup, SQLite/PostgreSQL compatibility, and transactional booking API with row-level locking.
- Verify: Prevent overselling under high concurrency.

### Milestone 2: Payment Gateway & Stripe Integration (Implementation Track)
- Task: Define modular Payment Gateway interface, implement Stripe Checkout adapter, support temporary reservations with timeouts, and construct webhook processor to finalize tickets.

### Milestone 3: Jinja2 Frontend, Admin Panel & Branding (Implementation Track)
- Task: Minimalist monospace styling, Admin dashboard to manage events, ticket tiers, branding settings, and view logs/check-ins. Branding must be dynamic.

### Milestone 4: Embeddable Widget (Implementation Track)
- Task: Lightweight vanilla JS widget loadable via `<script>`. Fetches tiers and initiates Stripe checkout session.

### Milestone 5: Final Acceptance & Hardening (Implementation Track & E2E Track)
- Phase 1: Run complete Tier 1-4 test suite, fix all issues until 100% pass.
- Phase 2: Spawn Challengers for white-box adversarial coverage hardening (Tier 5).
