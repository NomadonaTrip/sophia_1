---
phase: 04-approval-publishing-recovery
plan: 03
subsystem: publishing
tags: [apscheduler, sqlalchemy, asyncio, mcp, rate-limiting, recovery, notifications]

# Dependency graph
requires:
  - phase: 04-approval-publishing-recovery
    provides: Approval state machine, event bus, models (PublishingQueueEntry, RecoveryLog, GlobalPublishState), ContentDraft status field
  - phase: 01-foundation
    provides: Base, TimestampMixin, Settings, db engine, Client model
provides:
  - APScheduler-based publishing queue with cadence enforcement
  - MCP executor with retry logic (3x exponential backoff)
  - Per-platform rate limiter (Facebook 200/hr, Instagram 25/day)
  - Content recovery protocol (Facebook delete + Instagram manual fallback)
  - Stale content monitor (fires after 4hr un-reviewed content)
  - NotificationService dispatching to SSE event bus + registered channels
  - Global pause/resume for all publishing
  - CLI recovery trigger (recover N command)
  - APScheduler lifespan management in main.py
affects: [04-05-telegram-bot, 05-monitoring, 06-deployment]

# Tech tracking
tech-stack:
  added: [apscheduler>=3.10.0]
  patterns: [async executor with sync service bridge, NotificationService dispatch pattern, sliding window rate limiter, cadence enforcement via DB query]

key-files:
  created:
    - backend/src/sophia/publishing/__init__.py
    - backend/src/sophia/publishing/scheduler.py
    - backend/src/sophia/publishing/executor.py
    - backend/src/sophia/publishing/rate_limiter.py
    - backend/src/sophia/publishing/recovery.py
    - backend/src/sophia/publishing/stale_monitor.py
    - backend/src/sophia/publishing/notifications.py
    - backend/tests/test_publishing.py
    - backend/tests/test_recovery.py
  modified:
    - backend/src/sophia/main.py
    - backend/src/sophia/approval/cli.py
    - backend/pyproject.toml

key-decisions:
  - "APScheduler MemoryJobStore for tests, SQLAlchemyJobStore with separate unencrypted SQLite for production"
  - "MCP dispatch as NotImplementedError integration point (same pattern as Phase 2 research)"
  - "NotificationService as single dispatch point (executor/recovery call notification_service, not event_bus directly)"
  - "Instagram recovery falls back to manual_recovery_needed (ig-mcp has no delete support)"
  - "Naive datetime comparison for SQLite compatibility (SQLCipher strips timezone info)"
  - "handle_recovery_command bridges sync CLI to async recovery via asyncio.run()"

patterns-established:
  - "NotificationService pattern: single dispatch to SSE + registered channel callbacks with fault isolation"
  - "Sliding window rate limiter: prune-on-read, per-platform limits"
  - "Cadence enforcement via DB query: check existing scheduled posts before scheduling new ones"
  - "APScheduler lifespan in FastAPI: start in lifespan startup, shutdown in teardown"

requirements-completed: [APPR-03, APPR-04, SAFE-03, SAFE-04]

# Metrics
duration: 9min
completed: 2026-02-27
---

# Phase 04 Plan 03: Publishing Pipeline & Recovery Summary

**APScheduler publishing queue with MCP executor stubs, per-platform rate limiting, cadence enforcement, content recovery (Facebook delete + Instagram manual fallback), stale content monitor, and NotificationService dispatch to SSE + channels**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-27T21:56:20Z
- **Completed:** 2026-02-27T22:05:25Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- Complete publishing pipeline: scheduler, executor, rate limiter, notifications -- 19 tests passing
- Content recovery protocol with Facebook MCP delete and Instagram manual fallback -- 11 tests passing
- APScheduler started/stopped in FastAPI lifespan for production readiness
- CLI recovery trigger added (recover N command with reason and urgency)
- NotificationService as centralized dispatch point for all publishing events

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD -- Publishing scheduler, MCP executor, and rate limiter**
   - `e0683fd` (test: RED -- 19 failing tests for publishing pipeline)
   - `1c0a260` (feat: GREEN -- scheduler, executor, rate limiter, stale monitor, notifications, main.py lifespan)

2. **Task 2: TDD -- Content recovery protocol with Facebook delete, Instagram manual fallback, and CLI trigger**
   - `a026a73` (test: RED -- 11 failing tests for recovery protocol)
   - `3dcf840` (feat: GREEN -- recovery service, CLI extension)

## Files Created/Modified
- `backend/src/sophia/publishing/__init__.py` - Publishing module init
- `backend/src/sophia/publishing/scheduler.py` - APScheduler queue with cadence enforcement, pause/resume
- `backend/src/sophia/publishing/executor.py` - MCP dispatch with 3x retry backoff (2/4/8 min)
- `backend/src/sophia/publishing/rate_limiter.py` - Sliding window rate limiter (FB 200/hr, IG 25/day)
- `backend/src/sophia/publishing/recovery.py` - Recovery protocol with MCP delete + Instagram fallback
- `backend/src/sophia/publishing/stale_monitor.py` - APScheduler periodic job for stale content detection
- `backend/src/sophia/publishing/notifications.py` - NotificationService dispatching to SSE + registered channels
- `backend/src/sophia/main.py` - Added APScheduler lifespan management (start/stop)
- `backend/src/sophia/approval/cli.py` - Added recover N command with reason/urgency prompts
- `backend/pyproject.toml` - Added apscheduler>=3.10.0 dependency
- `backend/tests/test_publishing.py` - 19 TDD tests for publishing pipeline
- `backend/tests/test_recovery.py` - 11 TDD tests for recovery protocol

## Decisions Made
- APScheduler uses separate unencrypted SQLite job store (SQLCipher PRAGMA key incompatible with APScheduler's SQLAlchemyJobStore)
- MCP dispatch follows same NotImplementedError pattern as Phase 2 research -- tests mock at _dispatch_mcp level
- NotificationService is the single dispatch point: executor and recovery call it, not event_bus directly; plan 04-05 registers Telegram channel
- Instagram recovery falls back to manual_recovery_needed because ig-mcp has no delete support (listed as "future feature")
- Naive datetime comparison handles SQLite/SQLCipher stripping timezone info from DateTime columns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed timezone-aware/naive datetime comparison in stale monitor and cadence tests**
- **Found during:** Task 1 (GREEN phase -- tests 11 and 16 failing)
- **Issue:** SQLite returns naive datetimes even with DateTime(timezone=True); comparison with timezone-aware datetime.now(timezone.utc) fails
- **Fix:** Normalize to naive datetimes for DB queries and comparisons; add timezone to naive values when needed for arithmetic
- **Files modified:** backend/src/sophia/publishing/stale_monitor.py, backend/tests/test_publishing.py
- **Verification:** All 19 publishing tests pass
- **Committed in:** 1c0a260 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for SQLite compatibility. No scope creep.

## Issues Encountered
- SQLCipher's DateTime(timezone=True) columns store timezone-aware values but return naive ones -- required normalizing comparisons throughout the publishing module

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Publishing pipeline complete, ready for Telegram bot integration (04-05) to register as notification channel
- Recovery protocol ready for web UI trigger (already wired via REST endpoint in 04-01)
- Stale content monitor ready for production (register_stale_monitor needs db_session_factory wired in lifespan)
- MCP dispatch ready for trivial wiring when facebook-mcp-server and ig-mcp are configured

## Self-Check: PASSED

- All 12 key files: FOUND
- All 4 commits: FOUND (e0683fd, 1c0a260, a026a73, 3dcf840)
- All 30 tests: PASSED (19 publishing + 11 recovery)

---
*Phase: 04-approval-publishing-recovery*
*Completed: 2026-02-27*
