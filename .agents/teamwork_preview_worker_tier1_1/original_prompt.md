## 2026-06-09T00:46:25Z
You are a worker agent.
Your identity is: teamwork_preview_worker_tier1_1.
Your working directory is: c:\Development\openticket\.agents\teamwork_preview_worker_tier1_1.
Your task is to implement the Tier 1 Feature Coverage E2E test suite under tests/tier1_features/.

Implement at least 25 distinct test cases (using pytest and httpx/TestClient) covering the following files:

1. tests/tier1_features/test_event_mgmt.py:
   - test_create_event_api_success
   - test_list_events_api_success
   - test_retrieve_event_by_id_api_success
   - test_create_event_empty_name_fails
   - test_get_event_by_invalid_id_404
   - test_admin_dashboard_html_rendering (GET /admin or /admin/events, check response contains "OpenTicket Admin" or event titles)
   - test_admin_create_event_form_html (GET /admin/events/new or similar, check response has form inputs)

2. tests/tier1_features/test_tier_mgmt.py:
   - test_create_tier_success
   - test_list_tiers_success
   - test_create_tier_zero_price_success
   - test_create_tier_empty_name_fails
   - test_create_tier_negative_capacity_fails

3. tests/tier1_features/test_booking_reservations.py:
   - test_reserve_tickets_success
   - test_reserve_tickets_insufficient_capacity_fails
   - test_reserve_tickets_invalid_tier_404
   - test_reserve_tickets_zero_quantity_fails
   - test_reservation_capacity_decrement_reflected

4. tests/tier1_features/test_stripe_integration.py:
   - test_create_checkout_session_success (POST /api/bookings/{booking_session_id}/checkout returns mock Stripe URL)
   - test_create_checkout_session_invalid_booking_fails
   - test_stripe_webhook_completed_success (POST /api/webhooks/stripe marks booking as paid, generates ticket codes)
   - test_stripe_webhook_completed_invalid_booking_fails
   - test_stripe_webhook_completed_signature_verification (uses generate_stripe_signature helper)

5. tests/tier1_features/test_monospace_ui.py:
   - test_admin_branding_get_post
   - test_monospace_styles_in_html (checks HTML response contains monospace style classes or dark theme variables)
   - test_branding_customization_rendered_in_html (primary color, site logo, etc.)

6. tests/tier1_features/test_embeddable_widget.py:
   - test_widget_js_served (GET /static/widget.js or /frontend/widget.js)
   - test_widget_config_endpoint (GET /api/widget/config or similar returning branding configurations)
   - test_widget_cors_headers (verifies widget endpoints return appropriate CORS headers)

Note: Keep imports clean. Since some routes (like Stripe/Branding/Widget/Admin) might not be fully implemented in the backend yet, implement tests to expect these endpoints (e.g. POST /api/bookings/{id}/checkout, POST /api/webhooks/stripe, GET /admin/branding, GET /static/widget.js). Ensure your mock client calls use the routes from PROJECT.md.

MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Notify me once these tests are implemented.
