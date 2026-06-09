## 2026-06-08T22:41:16Z

Develop OpenTicket, an open-source, self-hosted ticket selling web application in Python that supports standing ticket tiers, maintains integrity under high-concurrency presales, integrates Stripe checkout, and provides an embeddable customer purchase widget.

Working directory: c:\Development\openticket
Integrity mode: demo

## Requirements

### R1. Backend API & Concurrency Control
Build a stateless Python FastAPI backend that manages events, ticket tiers, orders, and tickets. Implement a transactional ticket booking mechanism using database row-level locking (e.g. `SELECT FOR UPDATE` in SQLAlchemy) to guarantee that ticket inventory is never oversold during high-concurrency presales. The database layer must support SQLite (default) and PostgreSQL.
- **SQL Injection Prevention**: Use ORM-parameterized query execution exclusively. Do not write raw SQL strings or use string formatting for queries.

### R2. Extensible Payment Integration
Implement a modular Payment Gateway adapter interface. Implement a Stripe Checkout provider. The payment flow must support booking sessions with temporary ticket reservations (released if unpaid after a timeout) and handling webhook notifications to confirm purchases.

### R3. Hybrid Frontend & Underground Aesthetic
- **Visual Design**: The UI must be simple, clean, and minimalist, tailored for alternative and underground venues (e.g., high-contrast, industrial, or retro monospace typography, solid dark theme colors, avoiding standard AI-generated cookie-cutter gradients).
- **Branding Customization**: Support system-level branding options (custom colors, accent color, site name, logo URL) configurable via the Admin Panel and stored in the database.
- **Admin Dashboard**: A Jinja2-rendered administrative panel to create/edit events, set up ticket tiers (name, price, capacity), configure branding settings, and view orders/ticket check-ins.
- **Embeddable Purchase Widget**: A lightweight Vanilla Javascript & CSS widget that can be embedded into any external website via a simple `<script>` tag/iframe. The widget must fetch tiers and handle the customer purchase checkout process via REST API calls to the backend.

### R4. Security & Configuration
- All configurations (database URL, Stripe API keys, port, CORS headers) must be loaded from environment variables (`.env`).
- Ensure no sensitive API keys are printed in logs or leaked.
- Do not perform any file modifications outside the workspace directory (`c:\Development\openticket`).
- Avoid large downloads (> 200 MB).

## Acceptance Criteria

### Automated Verification
- [ ] Implement an automated test suite using `pytest` and FastAPI's `TestClient`.
- [ ] Include an integration test that simulates concurrent ticket purchases (using threading/multiprocessing or asyncio) to verify that a ticket tier with a capacity of N does not sell more than N tickets, returning clean error responses to overflow requests.
- [ ] Test checkout session creation and verify that a mock Stripe webhook successfully completes an order and produces valid ticket check-in codes.

### UI & Configuration
- [ ] Admin pages are rendered correctly using Jinja2 templates.
- [ ] The custom branding settings (logo, primary color, website title) dynamically apply to the checkout widget and success page.
- [ ] The visual design uses a clean, minimalist style (no generic AI gradients) suitable for alternative/underground venues.
