# E2E Test Infrastructure Design - Handoff Report

## 1. Observation
- The project is in a greenfield state. Running `list_dir` on `c:\Development\openticket` returns:
  ```json
  {"name":".agents", "isDir":true}
  {"name":".git", "isDir":true}
  {"name":".gitignore", "sizeBytes":"4894"}
  {"name":"ORIGINAL_REQUEST.md", "sizeBytes":"3501"}
  {"name":"requirements.txt", "sizeBytes":"189"}
  ```
  No application code (`src/` directory) or test code (`tests/` directory) has been implemented yet.
- `ORIGINAL_REQUEST.md` (lines 33-37) specifies the following automated verification requirements:
  ```markdown
  33: ### Automated Verification
  34: - [ ] Implement an automated test suite using `pytest` and FastAPI's `TestClient`.
  35: - [ ] Include an integration test that simulates concurrent ticket purchases (using threading/multiprocessing or asyncio) to verify that a ticket tier with a capacity of N does not sell more than N tickets, returning clean error responses to overflow requests.
  36: - [ ] Test checkout session creation and verify that a mock Stripe webhook successfully completes an order and produces valid ticket check-in codes.
  ```
- `.agents/orchestrator/PROJECT.md` (lines 22-26) outlines the API contracts for checkout and payment:
  ```markdown
  22: ## Interface Contracts
  23: ### Ticket Booking & Booking Session
  24: - `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Returns `booking_session_id`, `expires_at`.
  25: - `POST /api/bookings/{booking_session_id}/checkout`: Initiate checkout, return Stripe checkout URL.
  26: - `POST /api/webhooks/stripe`: Stripe webhook handler. Marks booking as paid and generates ticket check-in codes.
  ```
- `.agents/sub_orch_e2e/SCOPE.md` (lines 12-16) defines the E2E Testing milestones:
  ```markdown
  12: | 1 | Test Infra Design & Setup | Write `TEST_INFRA.md`, set up pytest structures, config, environment parsing, and mock Stripe frameworks. | None | IN_PROGRESS ... |
  13: | 2 | Tier 1 Feature Coverage | Implement >= 25 test cases covering the 5 key features in isolation. | M1 | PLANNED |
  14: | 3 | Tier 2 Boundary & Corner | Implement >= 25 test cases for boundaries, negative tests, and error scenarios. | M1 | PLANNED |
  15: | 4 | Tiers 3 & 4 Integration | Implement >= 5 cross-feature and >= 5 real-world scenario tests. | M2, M3 | PLANNED |
  ```

## 2. Logic Chain
1. Since the project is greenfield and does not contain any code in `src/` or `tests/`, the test infrastructure design must be independent, modular, and provide boilerplate configurations (`pytest.ini`, `conftest.py`, `helpers.py`) that can be dropped into the workspace as development begins (M1).
2. Given that FastAPI utilizes Python's asynchronous event loop, `pytest-asyncio` and `httpx.AsyncClient` are the logical choices to perform non-blocking HTTP E2E requests.
3. Because SQLite in default in-memory configurations does not isolate concurrent threads/sessions or enforce row-level locking (`SELECT FOR UPDATE`), concurrency tests must run against a local file-based SQLite database with WAL mode enabled, or point to a PostgreSQL instance via environment variables.
4. To test the Stripe integration using opaque-box testing without leaving security vulnerabilities (like bypassing signature checks):
   - Stripe's Checkout Redirect is mocked by patching the external SDK method (`stripe.checkout.Session.create`) to return a mock URL pointing to a fake redirect session.
   - Stripe's Webhook handling is tested by crafting valid JSON `checkout.session.completed` events and computing real cryptographic signatures via `stripe.WebhookSignature.compute_signature` using a test webhook secret.
5. To support Milestone validation, tests should be explicitly categorized into sub-directories supporting Tiers 1-4 and marked accordingly in `pytest.ini`.

## 3. Caveats
- **SQLite Row-Level Locking**: While SQLite parses `SELECT FOR UPDATE`, its locking behavior differs substantially from PostgreSQL. SQLite WAL mode mitigates write locking issues, but the implementer should test concurrency using PostgreSQL as well to ensure absolute presale integrity.
- **Frontend Assets**: The monospace UI and dynamic widget loading must be tested via backend template rendering validation (testing HTML structures and JS serving routes) since browser-based drivers (like Playwright/Selenium) are not specified in the requirements.

## 4. Conclusion
The proposed design in `analysis.md` and `proposed_TEST_INFRA.md` delivers a comprehensive E2E test infrastructure. It addresses Stripe mocking via genuine cryptographic verification, models async concurrency validation using `asyncio.gather`, and structures the `tests/` directory into 4 discrete Tiers to support all E2E requirements.

## 5. Verification Method
1. Inspect the written recommendation files inside the explorer directory:
   - Analysis report: `.agents/teamwork_preview_explorer_infra_2/analysis.md`
   - Test infrastructure draft: `.agents/teamwork_preview_explorer_infra_2/proposed_TEST_INFRA.md`
2. Once the project implementation starts, the design can be validated by copying `proposed_TEST_INFRA.md` to `c:\Development\openticket\TEST_INFRA.md`, creating the `tests/` directory structure, and running `pytest`.
