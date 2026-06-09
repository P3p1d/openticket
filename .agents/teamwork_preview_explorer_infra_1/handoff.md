# Handoff Report — E2E Test Infrastructure Design

This handoff report summarizes the analysis and recommendations for OpenTicket's E2E test infrastructure.

## 1. Observation
* **Greenfield Workspace**: Running `list_dir` on `c:\Development\openticket` showed:
  ```json
  {"name":".agents", "isDir":true}
  {"name":".git", "isDir":true}
  {"name":".gitignore", "sizeBytes":"4894"}
  {"name":"ORIGINAL_REQUEST.md", "sizeBytes":"3501"}
  {"name":"requirements.txt", "sizeBytes":"189"}
  ```
  Confirming that no source code currently exists under `src/` or `tests/`.
* **Testing Requirements & Acceptance Criteria**: `ORIGINAL_REQUEST.md` specifies:
  * "R1... transaction ticket booking mechanism using database row-level locking... to guarantee that ticket inventory is never oversold during high-concurrency presales."
  * "R2... Payment Gateway adapter interface. Implement a Stripe Checkout provider... and handling webhook notifications to confirm purchases."
  * "Acceptance Criteria... integration test that simulates concurrent ticket purchases... to verify that a ticket tier with a capacity of N does not sell more than N tickets... Test checkout session creation and verify that a mock Stripe webhook successfully completes an order..."
* **Project Specifications**: `PROJECT.md` identifies route contracts:
  * `POST /api/events/{event_id}/reserve`
  * `POST /api/bookings/{booking_session_id}/checkout`
  * `POST /api/webhooks/stripe`
* **Dependencies**: `requirements.txt` includes:
  * `pytest>=8.0.0`
  * `httpx>=0.27.0`
  * `stripe>=8.0.0`
  * `fastapi>=0.110.0`
  * `uvicorn[standard]>=0.28.0`
* **Test Structure Tiers**: `.agents/sub_orch_e2e/original_prompt.md` details:
  * Tier 1 (Feature Coverage >= 25 cases), Tier 2 (Boundary & Corner >= 25 cases), Tier 3 (Cross-feature >= 5 cases), Tier 4 (Real-world >= 5 cases).

## 2. Logic Chain
1. Since the application handles concurrency via database row-level locking (R1) and the E2E tests must verify this behavior under load, running FastAPI's `TestClient` in-process is insufficient because it handles requests synchronously/sequentially on a single thread.
2. Therefore, E2E concurrency tests require starting the FastAPI server in a background process/thread (e.g. via `uvicorn`) and making concurrent requests using `httpx.AsyncClient` from the test runner (Logical link: uvicorn live_server + httpx.AsyncClient -> concurrency simulation).
3. SQLite default write locks serialize operations and will fail under simultaneous updates. To enable concurrency under SQLite, the database must be configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) (Logical link: WAL mode -> sqlite concurrent writes support).
4. Since tests must run offline (CODE_ONLY mode) without calling the live Stripe API, we must mock checkout session redirects and signature validation.
5. Swapping the payment gateway implementation with a `MockPaymentGateway` allows returning local mock redirect URLs containing booking IDs.
6. The Stripe SDK uses HMAC-SHA256 signatures to verify webhook payloads against `STRIPE_WEBHOOK_SECRET`. Constructing equivalent HMAC signatures inside the test code allows offline signature validation to pass seamlessly without modifying/bypassing server validation logic (Logical link: HMAC calculation -> offline signature verification pass).

## 3. Caveats
* **Greenfield assumptions**: The recommendations assume the implementation team adheres to the directory layout in `PROJECT.md` and standard FastAPI dependency override mechanics.
* **Database Drivers**: Concurrency testing under SQLite is constrained by SQLite's single-writer database lock, even in WAL mode. While WAL mode enables concurrency, true row-level locking (`SELECT FOR UPDATE`) is only verified under PostgreSQL. The concurrency test suite should support configuring both database backends via the `TEST_DATABASE_URL` environment variable.

## 4. Conclusion
OpenTicket's E2E test suite can be implemented cleanly using `pytest` and `httpx`. The live server should run via `uvicorn` in a separate process, and Stripe webhook calls should be authenticated offline using custom HMAC signature generation. The test structure must be partitioned into `tests/tier1_feature_coverage/`, `tests/tier2_boundary_corner/`, `tests/tier3_cross_feature/`, and `tests/tier4_real_world/` to address all requested validation levels.

## 5. Verification Method
Verify recommendations by inspecting:
* `c:\Development\openticket\.agents\teamwork_preview_explorer_infra_1\analysis.md` (Detailed design, code setup, and conftest template).
* `c:\Development\openticket\.agents\teamwork_preview_explorer_infra_1\proposed_TEST_INFRA.md` (Formatted project documentation).
Once implemented, verify E2E suite passes by running:
```bash
pytest
```
from the root directory.
