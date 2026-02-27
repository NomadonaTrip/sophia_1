---
phase: 02-research-semantic-intelligence
plan: 02
subsystem: research, api
tags: [fastapi, circuit-breaker, mcp, research-engine, competitor-monitoring, digest, pydantic, pytest-asyncio]

# Dependency graph
requires:
  - phase: 01-client-foundation
    provides: Client model with market_scope, content_pillars, industry_vertical, geography fields
  - phase: 02-01
    provides: ResearchFinding, Competitor, CompetitorSnapshot models; FindingType, DECAY_WINDOWS, relevance_score; sync_to_lance; add_intelligence
provides:
  - CircuitBreaker for per-MCP-source failure isolation (5-failure threshold, 5-min cooldown)
  - ResearchScope for market-scoped query building from client profile
  - MCPSourceRegistry for source registration, dispatch, health reporting
  - run_research_cycle for daily per-client research orchestration
  - get_findings_for_content with relevance*confidence ranking and blocklist filtering
  - generate_daily_digest with findings grouped by type, freshness %, source health
  - monitor_competitors for daily primary and monthly watchlist monitoring
  - detect_opportunities with reactive/proactive classification
  - propose_new_competitors with deduplication
  - detect_competitor_inactivity for unusual quietness detection
  - compute_competitive_benchmarks for relative performance metrics
  - FastAPI research router with cycle, findings, digest, and health endpoints
  - Pydantic schemas: FindingResponse, ResearchDigest, DigestSummary, CompetitorAnalysis
affects: [02-03, 03-01, 04-01, 05-01, 06-01]

# Tech tracking
tech-stack:
  added: [fastapi 0.133.1, starlette 0.52.1, pytest-asyncio 1.3.0]
  patterns: [circuit-breaker-per-source, market-scoped-queries, expires-at-freshness-check, reactive-proactive-classification, id-based-ordering-for-deterministic-queries]

key-files:
  created:
    - backend/src/sophia/research/sources.py
    - backend/src/sophia/research/service.py
    - backend/src/sophia/research/competitor.py
    - backend/src/sophia/research/schemas.py
    - backend/src/sophia/research/router.py
    - backend/tests/test_research_service.py
    - backend/tests/test_competitor_monitoring.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "Freshness check uses expires_at > now instead of relevance_score -- expires_at is authoritative since created_at may not reflect actual finding age in test scenarios"
  - "Snapshot ordering by id DESC instead of created_at DESC -- deterministic ordering when timestamps are identical (SQLite func.now() granularity)"
  - "FastAPI router with placeholder _get_db_session dependency -- will be wired when app is assembled, keeping router testable independently"
  - "MCP dispatch raises NotImplementedError -- integration point for real MCP servers, all tests mock at _dispatch_query level"

patterns-established:
  - "Circuit breaker per MCP source: 5 failures to open, 5-min cooldown, auto-close on retry"
  - "Market-scoped queries: ResearchScope builds from client.market_scope JSON with fallback to direct fields"
  - "Partial research on source failure: None return from query_source means skip, cycle continues"
  - "Reactive vs proactive classification: competitor moves are reactive, market gaps are proactive"
  - "MonkeyPatch for async mock injection in pytest: mp.setattr for _sync_snapshot_to_lance"

requirements-completed: [RSRCH-01, RSRCH-02, RSRCH-03]

# Metrics
duration: 10min
completed: 2026-02-27
---

# Phase 02 Plan 02: Research Orchestration Engine Summary

**MCP-powered daily research cycle with market-scoped queries, circuit breaker fault isolation, competitor monitoring with reactive/proactive opportunity classification, and daily digest generation with freshness metrics**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-27T06:40:47Z
- **Completed:** 2026-02-27T06:51:01Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Research engine running daily per-client cycle: queries MCP sources scoped by location/industry/blocklist, creates structured findings with confidence scores, content angles (1-2 per finding), and time-based decay expiry
- Circuit breaker pattern isolating MCP source failures (5-failure threshold, 5-min cooldown) so partial research continues when one source goes down
- Competitor monitoring: daily for primary (3-5), monthly deep-scan for watchlist, with engagement metrics, content themes, and tone classification
- Opportunity detection classifying gaps as proactive ("nobody covers this, own it") and threats as reactive ("competitor is doing this better")
- Daily digest: findings grouped by type, time-sensitive alerts at top, research freshness percentage, source health report
- 47 tests passing across 2 test files (31 research service + 16 competitor monitoring), all MCP calls mocked

## Task Commits

Each task was committed atomically:

1. **Task 1: Research source registry, market-scoped queries, and research orchestration service** - `6f07bec` (feat)
2. **Task 2: Competitor monitoring service with opportunity detection and benchmarking** - `4bdd3d2` (feat)

## Files Created/Modified
- `backend/src/sophia/research/sources.py` - CircuitBreaker, ResearchScope, MCPSourceRegistry
- `backend/src/sophia/research/service.py` - run_research_cycle, get_findings_for_content, generate_daily_digest
- `backend/src/sophia/research/competitor.py` - monitor_competitors, detect_opportunities, propose_new_competitors, detect_competitor_inactivity, compute_competitive_benchmarks
- `backend/src/sophia/research/schemas.py` - FindingResponse, ResearchDigest, DigestSummary, CompetitorAnalysis
- `backend/src/sophia/research/router.py` - FastAPI router: POST cycle, GET findings, GET digest, GET health
- `backend/tests/test_research_service.py` - 31 tests for sources, service, digest
- `backend/tests/test_competitor_monitoring.py` - 16 tests for competitor monitoring, opportunity detection, benchmarks
- `backend/pyproject.toml` - Added fastapi and pytest-asyncio dependencies
- `backend/uv.lock` - Dependency lock file updated

## Decisions Made
- **Freshness uses expires_at not relevance_score**: The `generate_daily_digest` freshness check compares `expires_at > now` rather than computing `relevance_score` from `created_at`. This is more reliable because `created_at` is a server default that may not accurately reflect finding age when findings are created programmatically in the same transaction.
- **ID-based ordering for deterministic snapshot queries**: `detect_competitor_inactivity` orders by `CompetitorSnapshot.id DESC` instead of `created_at DESC` to ensure deterministic ordering when multiple snapshots have identical timestamps (SQLite `func.now()` second-level granularity).
- **FastAPI router with placeholder DB dependency**: The router uses a `_get_db_session` function that raises `NotImplementedError`. This keeps the router independently testable and makes the wiring point explicit for when the FastAPI app is assembled.
- **MCP dispatch as NotImplementedError integration point**: `MCPSourceRegistry._dispatch_query` raises `NotImplementedError` for real MCP servers. Tests mock at this level, making it trivial to wire real servers later.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added FastAPI and pytest-asyncio dependencies**
- **Found during:** Task 1 (router.py requires FastAPI, tests require pytest-asyncio)
- **Issue:** FastAPI and pytest-asyncio not in pyproject.toml dependencies
- **Fix:** `uv add fastapi` and `uv add --dev pytest-asyncio`
- **Files modified:** backend/pyproject.toml, backend/uv.lock
- **Verification:** All imports succeed, tests run
- **Committed in:** 6f07bec (Task 1 commit)

**2. [Rule 1 - Bug] Fixed freshness check using expires_at instead of relevance_score**
- **Found during:** Task 1 (test_includes_freshness_metric failing)
- **Issue:** Freshness computed from `relevance_score()` which uses `created_at`, but SQLite `server_default=func.now()` gives all findings the same creation timestamp regardless of their intended age
- **Fix:** Changed freshness check to compare `expires_at > now` with timezone-aware comparison
- **Files modified:** backend/src/sophia/research/service.py
- **Verification:** Freshness metric correctly reports 50% when 1 of 2 findings is expired
- **Committed in:** 6f07bec (Task 1 commit)

**3. [Rule 1 - Bug] Fixed snapshot ordering for inactivity detection**
- **Found during:** Task 2 (test_flags_50_pct_drop failing)
- **Issue:** `order_by(created_at.desc())` gave non-deterministic ordering when all snapshots created in same second
- **Fix:** Changed to `order_by(id.desc())` for deterministic most-recent-first ordering
- **Files modified:** backend/src/sophia/research/competitor.py
- **Verification:** Inactivity detection correctly flags >50% drop
- **Committed in:** 4bdd3d2 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations.

## User Setup Required
None - no external service configuration required. MCP servers will be configured when live research is enabled.

## Next Phase Readiness
- Research orchestration engine ready: all service functions exported and tested
- MCP integration point (`_dispatch_query`) ready to wire to real servers
- Competitor monitoring ready with full lifecycle: create, monitor, detect, benchmark
- Daily digest format ready for downstream consumers (content generation, Telegram bot)
- Plan 02-03 (Algorithm Detection) can build on research findings and competitor snapshots
- Phase 03 (Content Generation) can call `get_findings_for_content` for research-informed content

## Self-Check: PASSED

All 7 created files verified present. Both task commits (6f07bec, 4bdd3d2) verified in git log.

---
*Phase: 02-research-semantic-intelligence*
*Completed: 2026-02-27*
