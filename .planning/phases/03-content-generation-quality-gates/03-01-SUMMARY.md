---
phase: 03-content-generation-quality-gates
plan: 01
subsystem: content-generation
tags: [spacy, textstat, stylometrics, voice-alignment, prompt-engineering, sqlalchemy, pydantic]

# Dependency graph
requires:
  - phase: 01-foundation-client-intelligence
    provides: "Client model, VoiceProfile model, ClientService, VoiceService"
  - phase: 02-research-semantic-intelligence
    provides: "ResearchFinding model, research service get_findings_for_content()"
provides:
  - "ContentDraft, EvergreenEntry, FormatPerformance, RegenerationLog SQLAlchemy models"
  - "Stylometric voice alignment service (extract, baseline, drift scoring)"
  - "Platform-specific prompt builder with voice matching and few-shot examples"
  - "Content generation orchestrator with three-input validation and adaptive batch sizing"
  - "ContentGenerationError exception class"
affects: [03-02-quality-gates, 03-03-regeneration, 04-approval-workflow]

# Tech tracking
tech-stack:
  added: [spacy, en_core_web_sm]
  patterns: [stylometric-feature-extraction, voice-baseline-drift-detection, three-input-validation-gate, adaptive-batch-sizing, platform-specific-prompt-construction]

key-files:
  created:
    - "backend/src/sophia/content/__init__.py"
    - "backend/src/sophia/content/models.py"
    - "backend/src/sophia/content/schemas.py"
    - "backend/src/sophia/content/voice_alignment.py"
    - "backend/src/sophia/content/prompt_builder.py"
    - "backend/src/sophia/content/service.py"
    - "backend/tests/test_content_generation.py"
  modified:
    - "backend/src/sophia/exceptions.py"
    - "backend/tests/conftest.py"
    - "backend/pyproject.toml"
    - "backend/uv.lock"

key-decisions:
  - "cycle_id as plain nullable int without FK constraint -- cycle_runs table deferred to later phase"
  - "spaCy en_core_web_sm for NLP, installed via uv pip from GitHub release URL"
  - "FR19 thresholds: 25% sentence length, 20% vocabulary, 30% all others -- story mode 1.5x multiplier"
  - "Cold start returns neutral 0.5 score, not rejection -- graceful degradation"
  - "Prompt builder separates system prompt from examples text for flexibility"
  - "Story option count is half of feed option count (max 1, min option_count//2)"

patterns-established:
  - "Three-input validation gate: research + intelligence + voice must all exist before generation"
  - "Voice baseline from approved posts: mean/std per 9 stylometric features"
  - "Adaptive batch sizing: 2-5 options based on research richness scoring"
  - "Platform rules dict pattern: PLATFORM_RULES[platform][content_type] -> constraints"
  - "ContentGenerationError with reason field for informative three-input failures"

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-04]

# Metrics
duration: 11min
completed: 2026-02-27
---

# Phase 3 Plan 01: Content Generation Core Summary

**Voice-matched content generation with spaCy stylometric drift detection, three-input validation gate (research + intelligence + voice), adaptive 2-5 option batching, and platform-specific prompt construction for Facebook/Instagram feed and stories**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-27T15:59:39Z
- **Completed:** 2026-02-27T16:11:19Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- ContentDraft model with 29 columns covering all CONTEXT.md requirements (post copy, image prompt, hashtags, alt text, rich metadata, gate status, voice confidence, ranking)
- Voice alignment service extracting 9 stylometric features via spaCy + textstat with drift detection using FR19-calibrated thresholds
- Platform-specific prompt builder honoring locked decisions (Instagram 2200/120 chars, 3-5/0-1 hashtags, 1:1|4:5/9:16 ratios; Facebook 0-3 hashtags, 1.91:1)
- Content generation orchestrator enforcing three-input validation (research-first rule) with adaptive batch sizing and draft ranking

## Task Commits

Each task was committed atomically:

1. **Task 1: Content models, schemas, and voice alignment service** - `8e2d36f` (feat)
2. **Task 2: Prompt builder and content generation orchestrator service** - `7e8034e` (feat)

## Files Created/Modified
- `backend/src/sophia/content/__init__.py` - Content module init
- `backend/src/sophia/content/models.py` - ContentDraft, EvergreenEntry, FormatPerformance, RegenerationLog models
- `backend/src/sophia/content/schemas.py` - Pydantic schemas for drafts, voice alignment, platform rules
- `backend/src/sophia/content/voice_alignment.py` - Stylometric feature extraction, baseline computation, drift scoring
- `backend/src/sophia/content/prompt_builder.py` - System prompt construction, few-shot formatting, image prompt builder
- `backend/src/sophia/content/service.py` - Generation orchestrator with three-input validation, adaptive sizing, ranking
- `backend/tests/test_content_generation.py` - 42 tests covering all components
- `backend/src/sophia/exceptions.py` - Added ContentGenerationError with reason field
- `backend/tests/conftest.py` - Registered content models for test DB table creation
- `backend/pyproject.toml` - Added spacy dependency
- `backend/uv.lock` - Updated lock file

## Decisions Made
- **cycle_id without FK constraint:** cycle_runs table doesn't exist yet (future phase), so cycle_id is a plain nullable integer. FK can be added via migration when cycles are implemented.
- **spaCy installation via uv pip:** `python -m spacy download` requires pip; used direct GitHub release URL with `uv pip install` instead.
- **FR19 thresholds with story multiplier:** Default thresholds (25% sentence length, 20% vocabulary, 30% others) multiplied by 1.5 for stories since short text has higher natural variance.
- **Cold start neutral score:** Empty baseline returns 0.5 alignment (neutral) rather than 0.0 (rejection) -- prevents blocking content generation for new clients.
- **Story option count halved:** Instagram stories get floor(option_count/2) options since operator attention is lower for ephemeral content.
- **Prompt split into (system_prompt, examples_text):** Allows the generation caller to manage token budget between instructions and examples independently.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed spacy dependency not in pyproject.toml**
- **Found during:** Task 1 (voice alignment implementation)
- **Issue:** spacy was referenced in the plan but not in backend/pyproject.toml dependencies
- **Fix:** `uv add spacy` + `uv pip install en_core_web_sm` from GitHub release
- **Files modified:** backend/pyproject.toml, backend/uv.lock
- **Verification:** `import spacy; spacy.load('en_core_web_sm')` succeeds
- **Committed in:** 8e2d36f (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added ContentGenerationError exception class**
- **Found during:** Task 2 (service implementation)
- **Issue:** Plan referenced ContentGenerationError but it didn't exist in exceptions.py
- **Fix:** Added ContentGenerationError with message, detail, reason, suggestion fields
- **Files modified:** backend/src/sophia/exceptions.py
- **Verification:** Three-input validation tests raise ContentGenerationError correctly
- **Committed in:** 7e8034e (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both auto-fixes necessary for functionality. No scope creep.

## Issues Encountered
None - plan executed cleanly after dependency resolution.

## User Setup Required
None - no external service configuration required. spaCy model downloaded automatically.

## Next Phase Readiness
- Content generation core complete, ready for quality gates (03-02)
- ContentDraft model has gate_status and gate_report fields ready for gate pipeline
- Voice alignment service provides alignment scores for voice gate integration
- Prompt builder ready for regeneration guidance augmentation (03-03)

## Self-Check: PASSED

All 8 created files verified present. Both task commits (8e2d36f, 7e8034e) verified in git log. 42 tests passing.

---
*Phase: 03-content-generation-quality-gates*
*Completed: 2026-02-27*
