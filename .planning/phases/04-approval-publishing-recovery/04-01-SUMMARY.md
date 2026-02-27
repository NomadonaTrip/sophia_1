---
phase: 04-approval-publishing-recovery
plan: 01
subsystem: approval
tags: [fastapi, sqlalchemy, sse, asyncio, state-machine, pydantic]

# Dependency graph
requires:
  - phase: 03-content-generation
    provides: ContentDraft model, content router pattern, exception hierarchy
  - phase: 01-foundation
    provides: Base, TimestampMixin, Settings, db engine, Client model
provides:
  - Approval state machine (VALID_TRANSITIONS) enforcing all valid/invalid transitions
  - ApprovalEventBus for real-time SSE sync across interfaces
  - REST API endpoints for all approval actions (approve/reject/edit/skip/recover)
  - GET /api/events SSE streaming endpoint
  - 5 new DB models (PublishingQueueEntry, RecoveryLog, ApprovalEvent, NotificationPreference, GlobalPublishState)
  - ContentDraft approval metadata fields (approved_at, approved_by, publish_mode, operator_edits, custom_post_time)
  - InvalidTransitionError and ContentNotFoundError exceptions
  - CLI approval interface for Sprint 0
  - FastAPI app assembly (main.py) with all routers registered
affects: [04-02-frontend-approval-ui, 04-03-recovery-protocol, 04-05-telegram-bot, 05-publishing]

# Tech tracking
tech-stack:
  added: [sse-starlette, python-multipart]
  patterns: [async event bus with sync service layer, SSE via EventSourceResponse, state machine dict pattern]

key-files:
  created:
    - backend/src/sophia/approval/__init__.py
    - backend/src/sophia/approval/models.py
    - backend/src/sophia/approval/schemas.py
    - backend/src/sophia/approval/service.py
    - backend/src/sophia/approval/events.py
    - backend/src/sophia/approval/router.py
    - backend/src/sophia/approval/cli.py
    - backend/src/sophia/main.py
    - backend/tests/test_approval_service.py
    - backend/tests/test_approval_router.py
  modified:
    - backend/src/sophia/content/models.py
    - backend/src/sophia/exceptions.py
    - backend/src/sophia/config.py
    - backend/pyproject.toml
    - backend/tests/conftest.py

key-decisions:
  - "Sync service layer with async router pattern: service functions are synchronous (Phase 1-3 pattern), router publishes SSE events after calling service"
  - "State machine as dict (VALID_TRANSITIONS): simple, testable, no library dependency"
  - "SSE endpoint on separate events_router (no prefix): registered at app level for clean /api/events URL"
  - "Event bus uses asyncio.Queue per subscriber with QueueFull drop policy for slow consumers"
  - "GlobalPublishState as separate table: operator can pause all publishing globally"
  - "Recovery endpoint creates RecoveryLog audit trail alongside state transition"

patterns-established:
  - "State machine pattern: VALID_TRANSITIONS dict maps current_status -> set of allowed_next_statuses"
  - "Async event publishing in router after sync service call and db.commit()"
  - "SSE streaming via sse_starlette.EventSourceResponse wrapping async generator"
  - "App assembly in main.py: register all routers with CORS middleware"

requirements-completed: [APPR-01, APPR-02, APPR-05, APPR-06]

# Metrics
duration: 8min
completed: 2026-02-27
---

# Phase 04 Plan 01: Approval Backend Infrastructure Summary

**State machine approval service with SSE event bus, REST API, CLI, and 5 new DB models enforcing APPR-06 (no publish without approval)**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-27T20:21:30Z
- **Completed:** 2026-02-27T20:30:25Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Approval state machine fully tested with 29 test cases across service and router
- APPR-06 enforced at state machine level: draft->published is an invalid transition
- SSE event bus operational with publish/subscribe for real-time cross-interface sync
- REST API with correct HTTP semantics (200/404/409) and recovery endpoint
- CLI approval interface functional for Sprint 0 operator workflow
- FastAPI app assembly (main.py) created with all routers registered

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD -- Approval models, state machine, event bus, exceptions**
   - `19739de` (test: RED -- failing tests for state machine and event bus)
   - `f34789e` (feat: GREEN -- state machine, models, event bus, exceptions)

2. **Task 2: TDD -- REST router, SSE endpoint, CLI, app assembly**
   - `3cf4568` (test: RED -- failing tests for router endpoints)
   - `8d4c0f2` (feat: GREEN -- router, CLI, main.py, SSE endpoint)

## Files Created/Modified
- `backend/src/sophia/approval/__init__.py` - Approval module init
- `backend/src/sophia/approval/models.py` - 5 new ORM models (PublishingQueueEntry, RecoveryLog, ApprovalEvent, NotificationPreference, GlobalPublishState)
- `backend/src/sophia/approval/schemas.py` - Pydantic request/response schemas
- `backend/src/sophia/approval/service.py` - State machine with transition_draft, approve/reject/edit/skip, queue and health queries
- `backend/src/sophia/approval/events.py` - ApprovalEventBus with async publish/subscribe for SSE
- `backend/src/sophia/approval/router.py` - REST endpoints with SSE streaming via events_router
- `backend/src/sophia/approval/cli.py` - Sprint 0 CLI for interactive approval
- `backend/src/sophia/main.py` - FastAPI app assembly with all routers and CORS
- `backend/src/sophia/content/models.py` - ContentDraft extended with 6 approval metadata fields
- `backend/src/sophia/exceptions.py` - InvalidTransitionError and ContentNotFoundError added
- `backend/src/sophia/config.py` - Settings extended with telegram, timezone, stale content config
- `backend/pyproject.toml` - sse-starlette and python-multipart dependencies added
- `backend/tests/test_approval_service.py` - 17 TDD tests for state machine and event bus
- `backend/tests/test_approval_router.py` - 12 TDD tests for REST router and SSE
- `backend/tests/conftest.py` - Approval models registered for table creation

## Decisions Made
- Sync service layer with async router pattern preserves Phase 1-3 consistency while enabling SSE
- State machine as simple dict avoids external dependency; easy to extend in future phases
- SSE endpoint on separate router ensures clean URL (/api/events) without approval prefix
- Event bus drops events for slow consumers (QueueFull) rather than blocking publishers
- GlobalPublishState as dedicated table enables operator-level publishing pause
- Recovery endpoint creates RecoveryLog for full audit trail

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added python-multipart dependency**
- **Found during:** Task 2 (router implementation)
- **Issue:** FastAPI requires python-multipart for file upload endpoints (UploadFile)
- **Fix:** Added `python-multipart>=0.0.20` to pyproject.toml
- **Files modified:** backend/pyproject.toml
- **Verification:** Router imports and all tests pass
- **Committed in:** 8d4c0f2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for file upload endpoint. No scope creep.

## Issues Encountered
- Event bus subscribe test required async task scheduling (asyncio.ensure_future) to ensure queue was registered before publish -- fixed by restructuring test to yield control

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Approval backend complete, ready for frontend UI (04-02)
- Event bus ready for frontend SSE connection
- State machine ready for Telegram bot integration (04-05)
- Recovery endpoint ready for recovery protocol (04-03)
- main.py ready for production deployment wiring

## Self-Check: PASSED

- All 10 key files: FOUND
- All 4 commits: FOUND (19739de, f34789e, 3cf4568, 8d4c0f2)
- All 29 tests: PASSED

---
*Phase: 04-approval-publishing-recovery*
*Completed: 2026-02-27*
