---
phase: 05-performance-analytics-evaluation
plan: 04
subsystem: analytics
tags: [utm, publishing, tracking, analytics]

# Dependency graph
requires:
  - phase: 05-performance-analytics-evaluation (plan 02)
    provides: "inject_utm_into_copy and build_utm_url in analytics/utm.py"
  - phase: 04-approval-publishing-scheduling (plan 03)
    provides: "publishing executor with _dispatch_mcp integration point"
provides:
  - "UTM parameter injection wired into publishing dispatch path"
  - "campaign_slug derivation from content_pillar with 'general' fallback"
affects: [engagement-tracking, performance-metrics, analytics-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["UTM injection before MCP dispatch (publish_copy vs draft.copy separation)"]

key-files:
  created: []
  modified:
    - backend/src/sophia/publishing/executor.py
    - backend/tests/test_publishing.py

key-decisions:
  - "try/except ImportError for UTM import (graceful degradation when analytics module unavailable)"
  - "publish_copy variable separates UTM-tagged copy from DB-persisted draft.copy"
  - "campaign_slug derived from content_pillar with slugification and 'general' fallback"

patterns-established:
  - "UTM injection as pre-dispatch step: all URLs get UTM params before MCP, original copy untouched in DB"

requirements-completed: [ANLY-07]

# Metrics
duration: 2min
completed: 2026-02-28
---

# Phase 5 Plan 04: UTM Publishing Pipeline Wiring Summary

**UTM parameter injection wired into publishing executor, closing ANLY-07 verification gap for link tracking**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-28T14:48:20Z
- **Completed:** 2026-02-28T14:50:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Wired `inject_utm_into_copy` from `analytics/utm.py` into `publishing/executor.py` before `_dispatch_mcp`
- Added `_derive_campaign_slug` helper that slugifies `content_pillar` with "general" fallback
- All URLs in post copy now get UTM parameters (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`) before publishing
- Original `draft.copy` in DB is never mutated -- UTM-tagged copy is publish-only
- 3 new integration tests verify UTM injection in the dispatch path
- All 32 tests pass (20 existing publishing + 3 new UTM publishing + 9 UTM unit)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire inject_utm_into_copy into executor.py and add publishing tests** - `78de9e7` (feat)

**Plan metadata:** `b1d7fe2` (docs: complete plan)

## Files Created/Modified
- `backend/src/sophia/publishing/executor.py` - Added UTM import, _derive_campaign_slug helper, publish_copy injection before _dispatch_mcp
- `backend/tests/test_publishing.py` - 3 new tests: UTM in dispatched copy, no-URL passthrough, default campaign slug

## Decisions Made
- **try/except ImportError for UTM import:** Graceful degradation pattern matching existing decision_trace import in the same file (line 116). Publishing works even if analytics module is unavailable.
- **publish_copy variable isolation:** UTM-tagged copy is only used for the dispatch dict, never written back to `draft.copy`. Keeps DB copy clean for display and future regeneration.
- **Slugification via str.replace:** Simple approach (lowercase, spaces/underscores to hyphens) avoids adding a slug library. Sufficient for content pillar values.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ANLY-07 verification gap is closed: all published content now includes UTM tracking parameters
- Phase 5 (Performance, Analytics & Evaluation) is fully complete with all 4 plans done
- Ready for Phase 6 (Operator Experience & Polish)

## Self-Check: PASSED

- [x] executor.py exists with UTM injection
- [x] test_publishing.py exists with 3 new UTM tests
- [x] 05-04-SUMMARY.md exists
- [x] Commit 78de9e7 verified in git log

---
*Phase: 05-performance-analytics-evaluation*
*Completed: 2026-02-28*
