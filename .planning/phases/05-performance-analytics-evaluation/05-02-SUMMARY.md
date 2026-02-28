---
phase: 05-performance-analytics-evaluation
plan: 02
subsystem: analytics
tags: [vader-sentiment, anomaly-detection, mad-z-score, icp-comparison, share-of-voice, kpi-computation, campaign-grouping, conversion-funnel, briefing]

# Dependency graph
requires:
  - phase: 05-performance-analytics-evaluation
    provides: EngagementMetric, KPISnapshot, Campaign, CampaignMembership, ConversionEvent, IndustryBenchmark ORM models and Meta Graph API collector
  - phase: 04-approval-publishing-recovery
    provides: ApprovalEvent for internal quality KPIs
  - phase: 03-content-generation
    provides: ContentDraft with content_pillar, regeneration_count
  - phase: 02-research-intelligence
    provides: CompetitorSnapshot for share of voice scoring
provides:
  - Weekly KPI computation with standard engagement + internal quality metrics
  - Campaign auto-grouping by content pillar + calendar month
  - Conversion funnel tracking with stage counts and conversion rates
  - CAC/CLV computation when revenue data exists
  - VADER-based comment sentiment analysis (lazy-loaded)
  - MAD-based modified z-score anomaly detection per client and portfolio-wide
  - ICP audience demographics comparison against client personas
  - Share of voice scoring against competitor data
  - Morning brief with sage/amber/coral portfolio classification
  - Weekly strategic briefing with KPI trends, top posts, topic resonance, SOV
  - Telegram digest with 3 status-grouped messages
  - 5 new analytics router endpoints
affects: [05-03, morning-brief-integration, telegram-bot-digest]

# Tech tracking
tech-stack:
  added: []
  patterns: [mad-anomaly-detection-stdlib, sage-amber-coral-classification, funnel-stage-tracking, campaign-pillar-month-grouping]

key-files:
  created:
    - backend/src/sophia/analytics/sentiment.py
    - backend/src/sophia/analytics/anomaly.py
    - backend/src/sophia/analytics/icp.py
    - backend/src/sophia/analytics/sov.py
    - backend/src/sophia/analytics/briefing.py
    - backend/tests/test_analytics_services.py
  modified:
    - backend/src/sophia/analytics/kpi.py
    - backend/src/sophia/analytics/campaigns.py
    - backend/src/sophia/analytics/funnel.py
    - backend/src/sophia/analytics/router.py
    - backend/src/sophia/analytics/schemas.py
    - backend/tests/test_kpi.py
    - backend/tests/test_campaigns.py

key-decisions:
  - "stdlib statistics.median for MAD computation instead of numpy/scipy -- lighter dependency for single-value anomaly detection"
  - "Sage/amber/coral client classification: coral = high-severity anomaly OR 3+ week engagement decline; amber = medium anomaly OR approval_rate < 70%"
  - "Session.get() over deprecated Query.get() for SQLAlchemy 2.0 compatibility"
  - "ICP comparison uses fuzzy string matching for location and age range overlap percentage"

patterns-established:
  - "MAD-based anomaly detection using stdlib (no numpy dependency) for per-client metrics"
  - "Sage/amber/coral classification thresholds for portfolio health monitoring"
  - "Funnel stages as ordered constant list for conversion rate computation"
  - "Campaign auto-grouping by (content_pillar, calendar month) with slug generation"

requirements-completed: [ANLY-02, ANLY-04, ANLY-05, ANLY-06, ANLY-08, ANLY-09]

# Metrics
duration: 12min
completed: 2026-02-28
---

# Phase 5 Plan 02: Analytics Computation Layer Summary

**KPI aggregation, VADER sentiment, MAD anomaly detection, ICP comparison, SOV scoring, and sage/amber/coral portfolio briefing with 43 tests**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-28T13:03:36Z
- **Completed:** 2026-02-28T13:15:36Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- 8 analytics service modules covering KPI computation, campaign grouping, funnel tracking, sentiment analysis, anomaly detection, ICP comparison, share of voice, and briefing content
- Weekly KPI snapshots with standard engagement metrics (engagement_rate, save_rate, share_rate, reach/follower growth) plus internal quality KPIs (approval_rate, edit_frequency, rejection_rate, regeneration_count)
- Morning brief classifies entire portfolio into sage/amber/coral status with attention flags for coral clients
- 43 tests covering all computation services, graceful degradation (no data = null/empty), and edge cases
- 5 new router endpoints: summary (with live KPI computation + benchmark), posting-times, campaigns/group, plus updated portfolio endpoint

## Task Commits

Each task was committed atomically:

1. **Task 1: KPI computation, campaign grouping, funnel tracking, router endpoints** - `5e985fd` (feat)
2. **Task 2: Sentiment analysis, anomaly detection, ICP comparison, SOV, briefing content** - `5c0f284` (feat)

## Files Created/Modified

- `backend/src/sophia/analytics/kpi.py` - Weekly KPI computation with standard + internal quality metrics, benchmark comparison, posting time heatmap
- `backend/src/sophia/analytics/campaigns.py` - Campaign auto-grouping by content_pillar + month, campaign aggregate metrics
- `backend/src/sophia/analytics/funnel.py` - Conversion funnel tracking with stage counts, conversion rates, CAC/CLV
- `backend/src/sophia/analytics/sentiment.py` - VADER-based comment sentiment analysis with lazy import
- `backend/src/sophia/analytics/anomaly.py` - MAD-based modified z-score anomaly detection (per-client and portfolio-wide)
- `backend/src/sophia/analytics/icp.py` - ICP audience demographics comparison against client personas
- `backend/src/sophia/analytics/sov.py` - Share of voice scoring against competitor data
- `backend/src/sophia/analytics/briefing.py` - Morning brief (sage/amber/coral), weekly briefing, Telegram digest
- `backend/src/sophia/analytics/router.py` - 5 new endpoints (summary, posting-times, campaigns/group, etc.)
- `backend/src/sophia/analytics/schemas.py` - Added benchmark field to AnalyticsSummaryResponse
- `backend/tests/test_kpi.py` - 14 tests for KPI computation, trends, benchmarks, posting times
- `backend/tests/test_campaigns.py` - 10 tests for campaign grouping, metrics, funnel, CAC
- `backend/tests/test_analytics_services.py` - 19 tests for sentiment, anomaly, ICP, SOV, briefing

## Decisions Made

- **stdlib over numpy for anomaly detection:** Used `statistics.median` and list comprehensions instead of numpy/scipy for MAD computation. Keeps the dependency footprint lighter for single-value anomaly detection without sacrificing correctness (same algorithm as Phase 2).
- **Sage/amber/coral classification thresholds:** Coral = any high-severity anomaly (|z| > 4) OR engagement_rate declining 3+ consecutive weeks. Amber = any medium anomaly (|z| > 2.5) OR approval_rate < 70%. Sage = everything else. These provide clear, actionable categorization.
- **Session.get() over Query.get():** Migrated to SQLAlchemy 2.0 API to avoid deprecation warnings.
- **ICP fuzzy matching:** Age ranges are compared by computing overlap percentage between persona target range and actual audience distribution buckets. Location uses substring matching against city and country names.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed legacy SQLAlchemy Query.get() deprecation**
- **Found during:** Task 1 (test execution)
- **Issue:** `db.query(Model).get(id)` produces LegacyAPIWarning in SQLAlchemy 2.0
- **Fix:** Changed to `db.get(Model, id)` in kpi.py and test_campaigns.py
- **Files modified:** backend/src/sophia/analytics/kpi.py, backend/tests/test_campaigns.py
- **Committed in:** 5e985fd (Task 1 commit)

**2. [Rule 1 - Bug] Task 1 files already existed from 05-03 out-of-order commit**
- **Found during:** Task 1 (initial file creation)
- **Issue:** kpi.py, campaigns.py, funnel.py, router.py, schemas.py, test_kpi.py, test_campaigns.py were already committed in e2558c7 (05-03 commit that included 05-02 dependencies)
- **Fix:** Verified content correctness, applied only the legacy API fixes as incremental improvement
- **Files modified:** backend/src/sophia/analytics/kpi.py, backend/tests/test_campaigns.py
- **Committed in:** 5e985fd (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes were minor improvements. No scope creep. Task 2 files were genuinely new.

## Issues Encountered

- Task 1 files were pre-committed as part of 05-03 execution (out-of-order plan dependency). Content was verified correct, only SQLAlchemy 2.0 API fixes were applied as incremental improvements.

## User Setup Required

None - no external service configuration required. VADER sentiment is already installed (pyproject.toml from Plan 05-01).

## Next Phase Readiness

- Analytics computation layer complete -- all 8 service modules operational
- Plan 05-03 (decision quality evaluation) can use KPI trends, anomaly detection, and briefing content
- Morning brief and weekly briefing are ready for integration into the daily cycle
- Telegram digest ready for bot integration
- ICP comparison ready to be wired with actual Instagram audience demographics when platform tokens are configured

---
*Phase: 05-performance-analytics-evaluation*
*Completed: 2026-02-28*
