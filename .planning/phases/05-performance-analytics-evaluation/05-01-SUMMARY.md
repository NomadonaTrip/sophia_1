---
phase: 05-performance-analytics-evaluation
plan: 01
subsystem: analytics
tags: [httpx, meta-graph-api, apscheduler, utm, sqlalchemy, pydantic, engagement-metrics]

# Dependency graph
requires:
  - phase: 04-approval-publishing-recovery
    provides: PublishingQueueEntry with platform_post_id for metric collection, APScheduler infrastructure
provides:
  - 8 analytics ORM models (EngagementMetric, KPISnapshot, Campaign, CampaignMembership, ConversionEvent, DecisionTrace, DecisionQualityScore, IndustryBenchmark)
  - Meta Graph API v22 collector with httpx.AsyncClient
  - UTM parameter builder with URL injection into post copy
  - Daily scheduled metric collection via APScheduler at 6 AM
  - Analytics REST API with 5 endpoints
  - Algorithm-dependent/independent metric classification
  - Pydantic v2 response schemas for all analytics data
affects: [05-02, 05-03, publishing-executor-utm-wiring]

# Tech tracking
tech-stack:
  added: [httpx, vaderSentiment]
  patterns: [async-httpx-collector, algorithm-classification-tagging, utm-url-injection, cron-apscheduler-job]

key-files:
  created:
    - backend/src/sophia/analytics/__init__.py
    - backend/src/sophia/analytics/models.py
    - backend/src/sophia/analytics/collector.py
    - backend/src/sophia/analytics/utm.py
    - backend/src/sophia/analytics/schemas.py
    - backend/src/sophia/analytics/router.py
    - backend/tests/test_analytics_models.py
    - backend/tests/test_utm.py
    - backend/tests/test_collector.py
  modified:
    - backend/src/sophia/main.py
    - backend/tests/conftest.py
    - backend/pyproject.toml

key-decisions:
  - "Portfolio route defined before parameterized {client_id} routes to prevent FastAPI path conflict"
  - "Router _get_db wired directly (lazy SessionLocal import) matching approval router pattern"
  - "APScheduler cron job with sync wrapper using asyncio.run() for async-in-sync bridge"
  - "Reaction breakdown dicts flattened into separate metric rows (e.g. post_reactions_by_type_total_like)"

patterns-established:
  - "Algorithm classification at storage time: ALGO_DEPENDENT/ALGO_INDEPENDENT constant sets"
  - "Meta Graph API v22 metric names (views not impressions post-deprecation)"
  - "UTM injection via regex URL detection in post copy"
  - "FastAPI static routes before parameterized routes to avoid path conflicts"

requirements-completed: [ANLY-01, ANLY-03, ANLY-07]

# Metrics
duration: 9min
completed: 2026-02-28
---

# Phase 5 Plan 01: Analytics Data Foundation Summary

**Meta Graph API v22 engagement collector with algorithm-dependent/independent tagging, UTM builder, 8 ORM models, and daily APScheduler metric pull**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-28T12:51:11Z
- **Completed:** 2026-02-28T13:00:39Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments

- 8 analytics ORM models covering engagement metrics, KPIs, campaigns, conversions, decision traces, quality scores, and industry benchmarks
- Meta Graph API v22 collector that pulls page-level and per-post metrics via httpx, classifying each as algorithm-dependent or independent at storage time
- UTM parameter builder that injects tracking params into URLs found in post copy
- Daily metric collection scheduled at 6 AM operator timezone via APScheduler cron job
- Analytics REST API with 5 endpoints (metrics, summary, conversion, campaigns, portfolio)
- 43 tests covering models, UTM, classification, API parsing, error handling, scheduling, and router endpoints

## Task Commits

Each task was committed atomically:

1. **Task 1: Analytics ORM models, Pydantic schemas, and UTM builder** - `46890c9` (feat)
2. **Task 2: Meta Graph API collector, daily scheduling, and analytics router** - `3359c7a` (feat)

## Files Created/Modified

- `backend/src/sophia/analytics/__init__.py` - Analytics package init
- `backend/src/sophia/analytics/models.py` - 8 ORM models with algorithm classification constants
- `backend/src/sophia/analytics/collector.py` - Meta Graph API v22 metric puller with httpx
- `backend/src/sophia/analytics/utm.py` - UTM parameter builder with URL injection
- `backend/src/sophia/analytics/schemas.py` - Pydantic v2 response schemas
- `backend/src/sophia/analytics/router.py` - 5 API endpoints for analytics data
- `backend/src/sophia/main.py` - Router registration and daily metric pull scheduling
- `backend/tests/conftest.py` - Analytics model registration for test DB
- `backend/tests/test_analytics_models.py` - 22 model tests
- `backend/tests/test_utm.py` - 9 UTM tests
- `backend/tests/test_collector.py` - 21 collector, scheduler, and router tests
- `backend/pyproject.toml` - httpx and vaderSentiment dependencies

## Decisions Made

- **Portfolio route ordering:** Defined `/portfolio/summary` before `/{client_id}/...` routes to prevent FastAPI matching "portfolio" as an integer client_id (would produce 422 errors)
- **Router DB wiring:** Used the same lazy `SessionLocal` import pattern as the approval router (direct implementation, not placeholder)
- **APScheduler bridge:** Used `asyncio.run()` in a sync wrapper for the cron job, matching the existing publishing executor pattern
- **Reaction breakdown flattening:** Meta API returns dict values for reaction types; these are flattened into separate metric rows for queryability

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ContentDraft NOT NULL constraint in tests**
- **Found during:** Task 1 (test_analytics_models.py)
- **Issue:** ContentDraft requires `image_prompt` and `image_ratio` as NOT NULL fields; test was missing them
- **Fix:** Added `image_prompt` and `image_ratio` to ContentDraft creation in campaign membership and decision trace tests
- **Files modified:** backend/tests/test_analytics_models.py
- **Committed in:** 46890c9 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed FastAPI route path conflict for portfolio endpoint**
- **Found during:** Task 2 (test_collector.py router tests)
- **Issue:** `GET /api/analytics/portfolio/summary` was defined after `GET /api/analytics/{client_id}/metrics`, causing FastAPI to try parsing "portfolio" as an integer client_id (422 error)
- **Fix:** Moved portfolio route definition before all `{client_id}` parameterized routes
- **Files modified:** backend/src/sophia/analytics/router.py
- **Committed in:** 3359c7a (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## User Setup Required

None - no external service configuration required. Platform tokens are already in Settings from Phase 4.

## Next Phase Readiness

- Analytics data foundation is complete -- all models, collector, UTM builder, and router are in place
- Plan 05-02 (KPI computation, trend analysis, anomaly detection) can build on EngagementMetric data and KPISnapshot model
- Plan 05-03 (decision quality evaluation) can build on DecisionTrace and DecisionQualityScore models
- UTM injection into publishing pipeline is ready for wiring (Plan 05-02)

---
*Phase: 05-performance-analytics-evaluation*
*Completed: 2026-02-28*
