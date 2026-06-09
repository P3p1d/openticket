# Context: OpenTicket

## Environment Variables
The application expects the following configuration via environment variables or a `.env` file:
- `DATABASE_URL`: database connection string (e.g. `sqlite:///./openticket.db` or `postgresql://...`)
- `STRIPE_API_KEY`: Secret API key for Stripe integration
- `STRIPE_WEBHOOK_SECRET`: Webhook verification secret for Stripe events
- `PORT`: Server port (default: 8000)
- `CORS_ORIGINS`: Allowed CORS origins for the API and widget

## Code Layout
- Backend: FastAPI app in Python (`src/backend`)
- Templates: Jinja2 HTML files (`src/backend/templates`)
- Frontend/Widget: Vanilla HTML/JS/CSS (`src/frontend`)
- Tests: pytest suite (`tests/`)
