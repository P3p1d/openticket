# BRIEFING — 2026-06-09T00:41:28+02:00

## Mission
Manage the design, implementation, and verification of OpenTicket, an open-source, self-hosted Python/FastAPI ticket selling web application with Stripe checkout, robust concurrency controls, admin dashboard, and embeddable widget.

## 🔒 My Identity
- Archetype: Project Orchestrator
- Roles: orchestrator, user_liaison, human_reporter, successor
- Working directory: c:\Development\openticket\.agents\orchestrator
- Original parent: Sentinel
- Original parent conversation ID: 7870eb6c-8311-4983-ad79-53ed9d89504a

## 🔒 My Workflow
- **Pattern**: Project Pattern (Implementation Track + E2E Testing Track)
- **Scope document**: c:\Development\openticket\PROJECT.md
1. **Decompose**: Decompose the project into discrete milestones (Implementation Track and E2E Testing Track) representing module boundaries and test tiers.
2. **Dispatch & Execute**:
   - **Delegate (sub-orchestrator)**: Spawn a sub-orchestrator for each milestone to manage the Explorer -> Worker -> Reviewer -> Challenger -> Auditor cycle.
3. **On failure** (in this order):
   - Retry: nudge stuck agent or re-send task
   - Replace: spawn fresh agent with partial progress
   - Skip: proceed without (only if non-critical)
   - Redistribute: split stuck agent's remaining work
   - Redesign: re-partition decomposition
   - Escalate: report to parent (sub-orchestrators only, last resort; Project Orchestrator cannot escalate, must redesign)
4. **Succession**: Self-succeed at 16 spawns. Write handoff.md, cancel timers, spawn successor, and exit.
- **Work items**:
  1. Initialize project files and plans [pending]
  2. Implement E2E Testing Track [pending]
  3. Implement Backend API & DB (Milestone 1) [pending]
  4. Implement Extensible Payment & Stripe Integration (Milestone 2) [pending]
  5. Implement Frontend, Admin Panel & Custom Branding (Milestone 3) [pending]
  6. Implement Embeddable Javascript Widget (Milestone 4) [pending]
  7. Run Phase 1 E2E tests [pending]
  8. Run Phase 2 Adversarial Coverage Hardening [pending]
- **Current phase**: 1
- **Current focus**: Initialize project files and plans

## 🔒 Key Constraints
- Never write, modify, or create source code files directly (only metadata/state .md files in agent directories).
- Never run build/test commands yourself — require workers to do so.
- If Forensic Auditor reports INTEGRITY VIOLATION, the milestone FAILS UNCONDITIONALLY. Do not advance the milestone.
- Never reuse a subagent after it has delivered its handoff — always spawn fresh.
- Code-only network mode: no external web access, curl, wget, etc.

## Current Parent
- Conversation ID: 7870eb6c-8311-4983-ad79-53ed9d89504a
- Updated: 2026-06-09T00:41:28+02:00

## Key Decisions Made
- Chose Project Pattern with Dual Track (Implementation & E2E Testing).

## Team Roster
| Agent | Type | Work Item | Status | Conv ID |
|-------|------|-----------|--------|---------|
| sub_orch_e2e | self | E2E Testing Track | in-progress | 20e01b60-ac32-4eea-8cf1-59a881dcc39d |
| sub_orch_m1 | self | Milestone 1 (Backend API & DB) | in-progress | 517866d0-2597-47d8-98b1-2d0e547c9dbe |

## Succession Status
- Succession required: no
- Spawn count: 2 / 16
- Pending subagents: 20e01b60-ac32-4eea-8cf1-59a881dcc39d, 517866d0-2597-47d8-98b1-2d0e547c9dbe
- Predecessor: none
- Successor: not yet spawned

## Active Timers
- Heartbeat cron: task-13
- Safety timer: none

## Artifact Index
- c:\Development\openticket\ORIGINAL_REQUEST.md — Verbatim user request and requirements
- c:\Development\openticket\.agents\orchestrator\original_prompt.md — Original prompt log
