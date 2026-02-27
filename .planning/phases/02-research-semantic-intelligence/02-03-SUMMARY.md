---
phase: 02-research-semantic-intelligence
plan: 03
subsystem: research
tags: [scipy, mad-zscore, algorithm-detection, diagnostics, playbook, institutional-knowledge, lancedb]

# Dependency graph
requires:
  - phase: 02-research-semantic-intelligence/02-01
    provides: "PlatformIntelligence model, IntelligenceInstitutionalKnowledge model, sync_to_lance, intelligence service"
provides:
  - "Cross-portfolio algorithm shift detection via MAD-based z-scores"
  - "Platform playbook with required_to_play vs sufficient_to_win categorization"
  - "Plateau diagnostics with root cause analysis and experiment proposals"
  - "Weekly health checks for early decline detection"
  - "Anonymized institutional knowledge persistence from diagnostic insights"
  - "Semantic search for similar historical plateau patterns"
affects: [content-generation, daily-cycle, monitoring]

# Tech tracking
tech-stack:
  added: [scipy.stats.median_abs_deviation, numpy]
  patterns: [MAD-based z-score anomaly detection, root cause likelihood scoring, experiment proposal templates]

key-files:
  created:
    - backend/src/sophia/research/algorithm.py
    - backend/src/sophia/research/playbook.py
    - backend/src/sophia/research/diagnostics.py
    - backend/tests/test_algorithm_detection.py
    - backend/tests/test_diagnostics.py
  modified: []

key-decisions:
  - "Per-client PlatformIntelligence records for algorithm events instead of client_id=0, respecting FK constraint"
  - "MAD=0 (all identical values) returns None -- uniform identical changes are indistinguishable from noise without variance"
  - "Keyword-overlap deactivation threshold at 40% for conflicting playbook insights"
  - "SQL fallback for search_similar_diagnostics when LanceDB semantic search unavailable"

patterns-established:
  - "Algorithm detection: cross-client anomaly detection with minimum 3-client threshold and MAD-based z-scores"
  - "Playbook management: required_to_play vs sufficient_to_win categorization with deactivation of outdated insights"
  - "Diagnostic pipeline: detect plateau -> root cause analysis -> propose experiments -> persist institutional knowledge"
  - "Health check: lightweight weekly monitoring catching slow declines before plateaus form"

requirements-completed: [RSRCH-05, RSRCH-06, RSRCH-07, RSRCH-08, RSRCH-09]

# Metrics
duration: 11min
completed: 2026-02-27
---

# Phase 02 Plan 03: Analytical Intelligence Summary

**MAD-based cross-portfolio algorithm detection with platform playbook, plateau diagnostics with root cause analysis and experiment proposals, and institutional knowledge persistence**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-27T06:41:30Z
- **Completed:** 2026-02-27T06:53:06Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Cross-portfolio algorithm shift detection using scipy MAD-based z-scores across 3+ clients, with industry news cross-referencing and gradual 20-30% adaptation proposals
- Living platform playbook with required_to_play vs sufficient_to_win categorization, deactivation of outdated insights, and cross-client propagation of algorithm shifts
- Plateau diagnostics with 5 root cause categories (staleness, fatigue, competitor gains, algorithm, seasonal), structured experiment proposals with hypothesis/duration/success-metric/rollback
- Weekly health checks monitoring engagement trend, research freshness, profile completeness, and playbook coverage
- Anonymized institutional knowledge persistence from resolved diagnostics for cross-engagement learning with semantic search fallback

## Task Commits

Each task was committed atomically:

1. **Task 1: Cross-portfolio algorithm detection and platform playbook management** - `708e658` (feat)
2. **Task 2: Plateau diagnostics, institutional knowledge, and weekly health checks** - `38cd29e` (feat)

## Files Created/Modified
- `backend/src/sophia/research/algorithm.py` - Cross-portfolio anomaly detection: detect_algorithm_shift, analyze_shift_nature, propose_adaptation, log_algorithm_event
- `backend/src/sophia/research/playbook.py` - Living platform playbook: update_playbook, get_platform_playbook, categorize_insight, merge_algorithm_shift_into_playbook
- `backend/src/sophia/research/diagnostics.py` - Plateau detection, diagnostic reports, experiment proposals, weekly health checks, institutional knowledge persistence
- `backend/tests/test_algorithm_detection.py` - 22 tests for algorithm detection, playbook management, and categorization
- `backend/tests/test_diagnostics.py` - 16 tests for plateau detection, diagnostics, experiments, health checks, and institutional knowledge

## Decisions Made
- Per-client PlatformIntelligence records for algorithm events instead of client_id=0: the PlatformIntelligence table has a FK constraint on client_id referencing clients.id, so cross-portfolio events create one record per affected client
- MAD=0 (all identical engagement deltas) returns None: when all clients show exactly the same change, there is zero variance to distinguish signal from noise
- 40% keyword overlap threshold for deactivating conflicting playbook insights: balances catching true updates without over-deactivating loosely related entries
- SQL fallback for search_similar_diagnostics: when LanceDB semantic search is unavailable (empty table, model not loaded), falls back to SQL ILIKE industry matching

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FK constraint violation in log_algorithm_event**
- **Found during:** Task 1 (algorithm detection implementation)
- **Issue:** Plan specified client_id=0 for cross-portfolio algorithm events, but PlatformIntelligence.client_id has ForeignKey("clients.id") -- no client with id=0 exists
- **Fix:** Changed log_algorithm_event to accept client_ids parameter and create per-client records. Updated function signature to return list of records
- **Files modified:** backend/src/sophia/research/algorithm.py
- **Verification:** Test passes with valid client_id, FK constraint respected
- **Committed in:** 708e658 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix was necessary for correctness -- FK constraint would prevent any algorithm event logging. Per-client records actually better serve the architecture since each client can query their own platform intelligence.

## Issues Encountered
None beyond the FK constraint issue documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 analytical intelligence layer complete: algorithm detection, diagnostics, and platform playbook
- Ready for Phase 3 (content generation) which will use platform playbook insights to inform content strategy
- Weekly health checks can run immediately once daily cycle is implemented
- Institutional knowledge accumulates over time to improve diagnostic accuracy

## Self-Check: PASSED

All files verified present on disk. All commit hashes found in git log.

---
*Phase: 02-research-semantic-intelligence*
*Completed: 2026-02-27*
