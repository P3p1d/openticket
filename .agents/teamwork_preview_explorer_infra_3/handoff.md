# Handoff Report - E2E Test Infrastructure Design

## 1. Observation
- Observed project metadata and setup files in the workspace:
  - `c:\Development\openticket\requirements.txt` listing testing dependencies:
    ```
    9: pytest>=8.0.0
    10: httpx>=0.27.0
    ```
  - `c:\Development\openticket\.agents\orchestrator\PROJECT.md` specifying architecture and interface contracts:
    ```
    23: ### Ticket Booking & Booking Session
    24: - `POST /api/events/{event_id}/reserve`: Reserve tickets for a specific tier. Returns `booking_session_id`, `expires_at`.
    25: - `POST /api/bookings/{booking_session_id}/checkout`: Initiate checkout, return Stripe checkout URL.
    26: - `POST /api/webhooks/stripe`: Stripe webhook handler. Marks booking as paid and generates ticket check-in codes.
    ```
  - `c:\Development\openticket\.agents\sub_orch_e2e\SCOPE.md` defining testing tiers:
    ```
    13: | 2 | Tier 1 Feature Coverage | Implement >= 25 test cases covering the 5 key features in isolation. | M1 | PLANNED |
    14: | 3 | Tier 2 Boundary & Corner | Implement >= 25 test cases for boundaries, negative tests, and error scenarios. | M1 | PLANNED |
    15: | 4 | Tiers 3 & 4 Integration | Implement >= 5 cross-feature and >= 5 real-world scenario tests. | M2, M3 | PLANNED |
    ```
  - The project root currently contains no Python implementation files or `tests/` directory structure.

## 2. Logic Chain
- **Requirement for isolated testing**: E2E testing must validate full request lifecycles without mutating production databases or relying on network connections (as we are in CODE_ONLY mode).
- **Test DB choice**: In-memory SQLite cannot easily handle multiple DB sessions/connections simultaneously inside multi-threaded or async event loops. Therefore, a file-based temporary SQLite database (`test_openticket.db`) that is dropped and recreated for each test session ensures clean test isolation.
- **Stripe Mocking Strategy**:
  - Checkout Session Creation: Using `monkeypatch` to redirect the creation API mock-response keeps the client integration opaque-box (testing our internal endpoints directly).
  - Stripe Webhook Validation: Bypassing webhook verification logic would leave security logic unverified. Generating cryptographically signed SHA-256 HMAC tokens in the test client preserves secure E2E validation.
- **Test Organization (Tiers 1-4)**: Structuring tests by tier subdirectory (`tests/tier1_features/`, `tests/tier2_boundaries/`, etc.) enables developers to target specific verification phases and keeps the code structure clean as the test cases scale to the minimum 60 target.

## 3. Caveats
- No actual backend implementation exists yet (planned for subsequent Milestones 1-4). Test models and DB setup schemas in the configurations assume standard SQLAlchemy mappings.
- Concurrency behavior differs between SQLite (which serializes writes/locks via database-level locking) and PostgreSQL (which supports true row-level locks). While tests can run on both, the concurrency test implementation must handle SQLite operational lock exceptions gracefully.

## 4. Conclusion
- The proposed test infrastructure design using `pytest`, `httpx` (async client), a file-based SQLite database with transaction teardowns, Stripe checkout API monkeypatching, and HMAC signature-based webhook generation is robust, secure, and ready for integration.
- The design supports all four required test tiers and defines clear boundaries for testing concurrency.

## 5. Verification Method
- Inspect the generated analysis report at `c:\Development\openticket\.agents\teamwork_preview_explorer_infra_3\analysis.md`.
- Verify that the draft `TEST_INFRA.md` contents match the specifications of the original request and the sub-orchestrator's scope.
