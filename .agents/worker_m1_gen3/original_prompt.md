## 2026-06-09T00:57:03Z
You are the Worker (Gen 3) for Milestone 1.
Your working directory is c:\Development\openticket\.agents\worker_m1_gen3.
Please initialize your BRIEFING.md and progress.md in your working directory.

Read the previous challenger report at c:\Development\openticket\.agents\challenger_m1_1\challenge.md, and reviewer report at c:\Development\openticket\.agents\reviewer_m1_1_gen2\review.md.

Your task is to implement the following changes in the workspace:
1. In c:\Development\openticket\src\backend\routes\bookings.py:
   - In `create_checkout_session`: check if the booking session has expired or is cancelled. If `booking.expires_at <= now` or `booking.status == "expired"` or `booking.status == "cancelled"`, return HTTP 400 Bad Request. Update booking status to "expired" if it is expired but status is still "reserved" before returning.
   - In `stripe_webhook`: before updating the booking to "paid" and validating tickets, check if the booking is expired (expires_at <= now or status == "expired"). To do this safely under concurrency, first acquire a row-level lock on the TicketTier (select with_for_update()) for this booking. Compute current active reservations on the tier (excluding this booking). If active reservations + booking.quantity <= tier.capacity, allow the payment: set booking status to "paid" and tickets status to "valid". If it exceeds capacity, mark booking status as "failed", tickets status as "cancelled", and attempt to trigger a Stripe refund using `stripe.Refund.create(payment_intent=payment_intent)` if `payment_intent` is present in the session data.
2. In c:\Development\openticket\tests\test_concurrency_adversarial.py:
   - Modify `test_oversell_via_expired_reservation` to assert the corrected behavior. Specifically:
     - User A's webhook payment should complete with HTTP 200 (the webhook handler returns success, but with status failed internally in DB).
     - User A's booking status in the DB should be "failed" (or "expired").
     - User A's tickets should NOT be marked as "valid".
     - User B's booking status in DB should be "paid", and its tickets should be "valid".
     - The total number of valid tickets in the database for the tier must be exactly 5 (i.e. User B's tickets), verifying that capacity is NOT exceeded.
3. Run pytest from the root folder to confirm everything compiles and all tests pass (specifically test_concurrency.py and test_concurrency_adversarial.py).

Document the files modified, commands run, and pytest output in c:\Development\openticket\.agents\worker_m1_gen3\handoff.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
