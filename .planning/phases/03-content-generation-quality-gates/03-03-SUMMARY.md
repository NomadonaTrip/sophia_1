---
phase: 03-content-generation-quality-gates
plan: 03
subsystem: content-generation
tags: [regeneration, format-adaptation, ai-labeling, evergreen-bank, voice-calibration, fastapi-router, ema, guidance-patterns]

# Dependency graph
requires:
  - phase: 01-foundation-client-intelligence
    provides: "Client model, VoiceProfile model, ClientService"
  - phase: 02-research-semantic-intelligence
    provides: "ResearchFinding model, research service get_findings_for_content()"
  - phase: 03-content-generation-quality-gates
    plan: 01
    provides: "ContentDraft model, voice alignment service, content generation service, prompt builder"
  - phase: 03-content-generation-quality-gates
    plan: 02
    provides: "Quality gate pipeline (run_pipeline), GateStatus, QualityReport"
provides:
  - "Regeneration service with 3-attempt limit, guidance logging, and full quality gate pipeline"
  - "Guidance pattern analysis (5+ threshold) with voice profile update suggestions"
  - "Format performance tracking with EMA (alpha=0.3) and weighted format selection"
  - "Rejection pattern analysis (>80% threshold) and ranking calibration from operator choices"
  - "AI labeling compliance module (defaults OFF for text-only Meta posts, configurable rules)"
  - "Evergreen bank management (20-entry cap, 90-day auto-expiry)"
  - "Voice calibration sessions: A/B comparison, per-client, voice delta aggregation"
  - "Content API router with 18 endpoints (drafts, regeneration, calibration, formats, evergreen, guidance, AI labels)"
  - "CalibrationSession and CalibrationRound SQLAlchemy models"
  - "RegenerationLimitError exception class"
affects: [04-approval-workflow, 05-analytics-monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns: [regeneration-with-guidance-loop, ema-format-performance, keyword-cluster-guidance-analysis, ab-voice-calibration, configurable-ai-labeling-rules, evergreen-bank-cap-expiry, content-api-router-18-endpoints]

key-files:
  created:
    - "backend/src/sophia/content/ai_label.py"
    - "backend/src/sophia/content/router.py"
    - "backend/tests/test_content_lifecycle.py"
  modified:
    - "backend/src/sophia/content/service.py"
    - "backend/src/sophia/content/models.py"
    - "backend/src/sophia/exceptions.py"
    - "backend/tests/conftest.py"

key-decisions:
  - "Regeneration re-validates three inputs (research-first rule applies to regen too)"
  - "Guidance pattern clustering uses keyword matching (7 clusters), not LLM -- fast and deterministic"
  - "Format weights use exploration weight 0.15 for untested formats -- ensures discovery"
  - "Rejection pattern threshold >80% with minimum 3 samples to avoid noise"
  - "Calibration total_rounds clamped to 5-10 range (locked decision)"
  - "Voice deltas simplified to 3 dimensions: brevity, formality, directness"
  - "AI label rules as configurable dict ready for EU AI Act (Aug 2026) changes"
  - "Router uses placeholder DB dependency for wiring during app assembly (same as research router)"

patterns-established:
  - "Regeneration loop: load draft -> check limit -> validate inputs -> generate -> gate pipeline -> log guidance"
  - "EMA rolling averages (alpha=0.3) for format performance -- weights recent data more"
  - "Keyword cluster analysis for detecting repeated operator preferences across sessions"
  - "A/B calibration pattern: generate pair -> record choice -> compute delta -> aggregate"
  - "Configurable rules dict pattern for compliance (AI_LABEL_RULES) -- easy to update"
  - "Evergreen bank lifecycle: cap enforcement + time-based expiry + usage tracking"

requirements-completed: [CONT-05, CONT-06, CONT-08, CONT-09]

# Metrics
duration: 14min
completed: 2026-02-27
---

# Phase 3 Plan 03: Content Lifecycle Summary

**Regeneration with 3-attempt limit and guidance learning, A/B voice calibration sessions, EMA-weighted format adaptation, AI labeling compliance (Meta text-only OFF), evergreen bank (20-cap, 90-day expiry), and full 18-endpoint content API router**

## Performance

- **Duration:** 14 min
- **Started:** 2026-02-27T16:31:55Z
- **Completed:** 2026-02-27T16:45:56Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Regeneration service enforcing 3-attempt limit with full quality gate pipeline (no shortcuts, locked decision), guidance pattern analysis detecting 5+ occurrence themes with voice profile update suggestions
- Voice calibration sessions with A/B comparison rounds (per-client only), voice delta computation, aggregated preference adjustments on finalization
- Format performance tracking with EMA (alpha=0.3), performance-weighted format selection with exploration weight for untested formats, natural language adaptation explanations
- Content API router exposing 18 endpoints covering the complete content lifecycle: drafts, regeneration, calibration, format adaptation, evergreen bank, guidance patterns, ranking calibration, and AI labeling rules
- AI labeling compliance module with configurable per-platform rules, correctly defaulting OFF for text-only Meta posts while being ready for regulation changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Regeneration service, format adaptation, AI labeling, and evergreen bank** - `8df79b0` (feat)
2. **Task 2: Voice calibration sessions and content API router** - `31fd281` (feat)

## Files Created/Modified
- `backend/src/sophia/content/ai_label.py` - AI labeling compliance: rules dict, should_apply, apply_label, requirements summary
- `backend/src/sophia/content/router.py` - Content API router with 18 endpoints (drafts, regen, calibration, formats, evergreen, guidance, AI labels)
- `backend/tests/test_content_lifecycle.py` - 43 tests covering regeneration, format adaptation, AI labeling, evergreen bank, calibration, and router endpoints
- `backend/src/sophia/content/service.py` - Extended with regeneration, format adaptation, guidance analysis, rejection patterns, ranking calibration, evergreen management, and voice calibration session logic
- `backend/src/sophia/content/models.py` - Added CalibrationSession and CalibrationRound models
- `backend/src/sophia/exceptions.py` - Added RegenerationLimitError exception class
- `backend/tests/conftest.py` - Registered CalibrationSession and CalibrationRound models for test DB

## Decisions Made
- **Regeneration re-validates three inputs:** Research-first rule applies to regeneration too -- no content without fresh research, intelligence, and voice.
- **Keyword cluster guidance analysis:** 7 predefined clusters (humor, shorter, casual, formal, emotional, engaging, simpler) matched by keyword presence. Fast and deterministic -- no LLM needed.
- **Exploration weight 0.15:** Untested formats get 15% weight to ensure format discovery even when performance data is sparse.
- **Rejection pattern minimum sample 3:** Avoids flagging categories with too few observations as high-rejection.
- **Calibration rounds clamped 5-10:** Locked decision from CONTEXT.md (5-10 rounds per session).
- **Voice deltas as 3 dimensions:** Brevity, formality, and directness preferences -- simple and interpretable for operator communication.
- **AI label rules as configurable dict:** Easy to update when EU AI Act (August 2026) or platform policy changes require text labels.
- **Router placeholder DB dependency:** Same pattern as research router -- keeps router independently testable, explicit wiring point for app assembly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added RegenerationLimitError exception class**
- **Found during:** Task 1 (regeneration service implementation)
- **Issue:** Plan referenced RegenerationLimitError but it didn't exist in exceptions.py
- **Fix:** Added RegenerationLimitError with informative message and suggestion to start fresh
- **Files modified:** backend/src/sophia/exceptions.py
- **Verification:** Regeneration at limit correctly raises RegenerationLimitError
- **Committed in:** 8df79b0 (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added CalibrationSession and CalibrationRound models**
- **Found during:** Task 1 (preparing for Task 2 calibration implementation)
- **Issue:** Plan referenced CalibrationSession and CalibrationRound but models didn't exist
- **Fix:** Added both models to content/models.py with appropriate columns and relationships
- **Files modified:** backend/src/sophia/content/models.py, backend/tests/conftest.py
- **Verification:** Calibration session creation and round generation work correctly
- **Committed in:** 8df79b0 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both missing critical)
**Impact on plan:** Both auto-fixes necessary for functionality. Models and exception needed to exist before service code could reference them. No scope creep.

## Issues Encountered
- Rejection pattern test initially used exactly 80% threshold (4/5 = 0.80) but the function uses strict > 0.80. Fixed test to use 5/6 (83%) to clearly exceed threshold. Not a code bug -- test expectation aligned with implementation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Content lifecycle complete: generation, quality gates, regeneration, calibration, format adaptation, AI labeling, evergreen bank, and full API
- Content API router ready for wiring during app assembly (Phase 6)
- Regeneration guidance learning feeds voice profile evolution (compounding intelligence)
- Format adaptation data feeds from Phase 5 analytics pipeline (update_format_performance called when engagement data available)
- Approval workflow (Phase 4) can query content drafts via service layer and mark approved/rejected

## Self-Check: PASSED

All 7 files verified present. Both task commits (8df79b0, 31fd281) verified in git log. 126 total tests passing (43 lifecycle + 42 content generation + 41 quality gates).

---
*Phase: 03-content-generation-quality-gates*
*Completed: 2026-02-27*
