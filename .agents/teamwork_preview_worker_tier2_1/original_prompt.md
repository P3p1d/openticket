## 2026-06-09T00:54:47+02:00
Implement the Tier 2 Boundary & Corner Cases E2E test suite under tests/tier2_boundaries/.

Implement at least 25 distinct test cases (using pytest and httpx/TestClient) covering:

1. tests/tier2_boundaries/test_validation_errors.py:
   - test_create_event_long_name
   - test_create_event_past_date
   - test_create_tier_negative_price_fails
   - test_create_tier_zero_price_success
   - test_create_tier_negative_capacity_fails
   - test_create_tier_zero_capacity_fails
   - test_reserve_tickets_negative_quantity_fails
   - test_reserve_tickets_non_existent_event_404
   - test_reserve_tickets_mismatched_event_tier_400

2. tests/tier2_boundaries/test_capacity_limits.py:
   - test_reserve_exactly_capacity
   - test_reserve_exceeding_capacity_by_one_fails
   - test_reserve_when_capacity_is_zero_fails
   - test_multiple_reserves_summing_exactly_to_capacity
   - test_multiple_reserves_exceeding_capacity_fails

3. tests/tier2_boundaries/test_reservation_timeouts.py:
   - test_checkout_expired_reservation_fails
   - test_expired_reservations_released_and_reclaimed
   - test_checkout_just_before_expiry_success
   - test_double_cleanup_idempotent

4. tests/tier2_boundaries/test_webhook_security.py:
   - test_stripe_webhook_missing_signature_fails
   - test_stripe_webhook_invalid_signature_format_fails
   - test_stripe_webhook_expired_signature_fails
   - test_stripe_webhook_incorrect_secret_fails
   - test_stripe_webhook_empty_payload_fails
   - test_stripe_webhook_non_checkout_event_ignored

5. tests/tier2_boundaries/test_sql_injection.py:
   - test_sql_injection_event_id_fails
   - test_sql_injection_tier_name_escaped

If any routes are missing or bugs exist in the backend (e.g., reservation release timeout checking), implement/fix them so the tests pass genuinely.
