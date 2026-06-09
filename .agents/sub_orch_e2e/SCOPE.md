# Scope: E2E Testing Track

## Architecture
- **E2E Test Architecture**: Opaque-box, requirement-driven verification using FastAPI's `TestClient` or HTTP requests to a running app instance.
- **Mocking**: Stripe APIs are mocked. Standard Stripe webhooks are simulated by posting mock events directly to the webhook handler.
- **Database**: Each test run resets/initializes a test SQLite database.
- **Visual & UI Checks**: Validate HTML layout, elements, branding fields in the Jinja2 template responses.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Test Infra Design & Setup | Write `TEST_INFRA.md`, set up pytest structures, config, environment parsing, and mock Stripe frameworks. | None | DONE |
| 2 | Tier 1 Feature Coverage | Implement >= 25 test cases covering the 5 key features in isolation. | M1 | DONE |
| 3 | Tier 2 Boundary & Corner | Implement >= 25 test cases for boundaries, negative tests, and error scenarios. | M1 | IN_PROGRESS (Worker: 19a59e3c-a331-4380-8adb-eb90c1c31250) |
| 4 | Tiers 3 & 4 Integration | Implement >= 5 cross-feature and >= 5 real-world scenario tests. | M2, M3 | PLANNED |
| 5 | Publish TEST_READY.md | Synthesize test suite statistics and output `TEST_READY.md` at project root. | M4 | PLANNED |

## Interface Contracts
- **Event & Tier Management**:
  - API to create/manage events and ticket tiers (to be verified via standard FastAPI routes/admin forms).
- **Booking Session & Reservations**:
  - `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Returns `booking_session_id`, `expires_at`.
- **Checkout & Payments**:
  - `POST /api/bookings/{booking_session_id}/checkout`: Returns Stripe checkout URL.
  - `POST /api/webhooks/stripe`: Receives Stripe webhook payloads to confirm payment and generate tickets.
- **Branding**:
  - Custom colors, logo, site name configurable via admin settings and applied to checkout/widget.
