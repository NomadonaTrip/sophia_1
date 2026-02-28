---
phase: 04-approval-publishing-recovery
plan: 06
subsystem: publishing
tags: [image-upload, stale-monitor, apscheduler, fastapi, sqlalchemy]

# Dependency graph
requires:
  - phase: 04-approval-publishing-recovery
    provides: "Upload endpoint, PublishingQueueEntry model, stale_monitor module, executor image validation"
provides:
  - "ContentDraft.image_url column wired end-to-end from upload to publish"
  - "Stale content monitor actively running every 30 minutes"
affects: [05-monitoring-analytics, publishing-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared _session_factory for all lifespan services"
    - "getattr fallback for optional model fields in scheduler"

key-files:
  created: []
  modified:
    - "backend/src/sophia/content/models.py"
    - "backend/src/sophia/approval/router.py"
    - "backend/src/sophia/publishing/scheduler.py"
    - "backend/src/sophia/main.py"
    - "backend/tests/test_publishing.py"
    - "backend/tests/test_approval_router.py"

key-decisions:
  - "Shared _session_factory defined once in lifespan, reused by stale monitor and Telegram bot"
  - "getattr(draft, 'image_url', None) in scheduler for backward compatibility"

patterns-established:
  - "Single _session_factory pattern: define once at lifespan top, pass to all services"

requirements-completed: [APPR-03, APPR-06]

# Metrics
duration: 11min
completed: 2026-02-28
---

# Phase 4 Plan 06: Gap Closure Summary

**Image upload wired end-to-end (ContentDraft.image_url -> PublishingQueueEntry.image_url) and stale content monitor activated in lifespan**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-28T07:30:00Z
- **Completed:** 2026-02-28T07:41:20Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Closed the blocker gap: upload endpoint now persists image_url to ContentDraft and schedule_publish copies it to PublishingQueueEntry, enabling the executor to find image_url and proceed with auto-publish
- Activated stale content monitor: register_stale_monitor() called with shared _session_factory in lifespan, runs every 30 minutes to detect content stuck in review > 4 hours
- Added 2 new tests (upload sets image_url, schedule_publish copies image_url), all 33 publishing+approval tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire image_url from upload through publish pipeline** - `5f910b0` (fix)
2. **Task 2: Wire stale content monitor in application lifespan** - `badf2d1` (fix)

## Files Created/Modified
- `backend/src/sophia/content/models.py` - Added image_url column (String 500, nullable) to ContentDraft
- `backend/src/sophia/approval/router.py` - Upload endpoint sets draft.image_url and commits
- `backend/src/sophia/publishing/scheduler.py` - schedule_publish copies draft.image_url to entry.image_url
- `backend/src/sophia/main.py` - Uncommented register_stale_monitor, shared _session_factory
- `backend/tests/test_publishing.py` - Added test_schedule_publish_copies_image_url, updated _make_draft helper
- `backend/tests/test_approval_router.py` - Added TestUploadImageSetsDraftImageUrl

## Decisions Made
- Shared _session_factory: defined once at the top of lifespan (before stale monitor registration), reused by both stale monitor and Telegram bot. Eliminates duplicate definitions and ensures consistent lazy-import pattern.
- Used getattr(draft, "image_url", None) in scheduler for backward compatibility with any drafts that might lack the column during migration.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 4 gap closure complete: both verification gaps (image upload blocker + stale monitor warning) resolved
- All Phase 4 success criteria now fully satisfied
- Ready for Phase 5 (Monitoring & Analytics)

## Self-Check: PASSED

All 6 modified files verified on disk. Both commit hashes (5f910b0, badf2d1) found in git log.

---
*Phase: 04-approval-publishing-recovery*
*Completed: 2026-02-28*
