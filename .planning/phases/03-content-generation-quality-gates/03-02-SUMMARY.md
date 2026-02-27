---
phase: 03-content-generation-quality-gates
plan: 02
subsystem: content-generation
tags: [quality-gates, sensitivity, plagiarism, difflib, ai-detection, brand-safety, voice-alignment, auto-fix]

# Dependency graph
requires:
  - phase: 01-foundation-client-intelligence
    provides: "Client model with industry, guardrails, competitors fields"
  - phase: 02-research-semantic-intelligence
    provides: "ResearchFinding model, research service get_findings_for_content()"
  - phase: 03-content-generation-quality-gates
    plan: 01
    provides: "ContentDraft model, voice alignment service (compute_voice_baseline, score_voice_alignment), content generation service"
provides:
  - "Sequential quality gate pipeline with auto-fix-once retry (run_pipeline)"
  - "Six individual gates: sensitivity, voice_alignment, plagiarism_originality, ai_pattern_detection, research_grounding, brand_safety"
  - "GateStatus enum, GateResult dataclass, QualityReport with summary badges and JSON serialization"
  - "Gate tracking: track_gate_failure(), check_systemic_gate_issues(), get_gate_statistics()"
  - "Quality gate integration in generate_content_batch (rejected drafts filtered, all-rejected error)"
affects: [03-03-regeneration, 04-approval-workflow]

# Tech tracking
tech-stack:
  added: [difflib]
  patterns: [sequential-gate-pipeline, auto-fix-once-retry, industry-calibrated-sensitivity, dual-layer-plagiarism-check, ai-cliche-regex-detection, sentence-uniformity-cv-scoring, per-client-brand-guardrails, systemic-issue-detection-30pct-threshold]

key-files:
  created:
    - "backend/src/sophia/content/quality_gates.py"
  modified:
    - "backend/src/sophia/content/service.py"
    - "backend/tests/test_quality_gates.py"

key-decisions:
  - "Gate dispatch table pattern: _GATE_FUNCTIONS dict maps gate names to functions for testability and extensibility"
  - "Auto-fix returns None for voice alignment: too hard to fix deterministically, requires LLM in production"
  - "Sensitivity gate uses regex+keyword approach with industry-calibrated thresholds; LLM evaluation deferred to runtime"
  - "AI cliche detection: 17 regex patterns + coefficient of variation (CV < 0.3) for sentence uniformity"
  - "Plagiarism dual-layer: semantic via LanceDB (threshold 0.85) + text via difflib SequenceMatcher (threshold 0.60)"
  - "Gate statistics query ContentDraft.gate_report JSON rather than separate tracking table -- simpler schema"
  - "Cold start voice alignment bypass at <5 approved posts -- locked decision from CONTEXT.md"

patterns-established:
  - "Sequential gate pipeline with locked execution order and early termination on rejection"
  - "Auto-fix-once retry: exactly one fix attempt per gate failure, no infinite loops"
  - "QualityReport.to_dict() for JSON-safe serialization stored on ContentDraft.gate_report"
  - "Per-client guardrails loaded from Client model (guardrails, competitors JSON fields)"
  - "Systemic issue detection at >30% failure rate with gate-specific recommendations"
  - "Rejected drafts persisted for learning but excluded from operator approval queue"

requirements-completed: [CONT-07, SAFE-05, SAFE-06]

# Metrics
duration: 13min
completed: 2026-02-27
---

# Phase 3 Plan 02: Quality Gate Pipeline Summary

**Sequential six-gate quality pipeline (sensitivity -> voice -> plagiarism -> AI detection -> research grounding -> brand safety) with auto-fix-once retry, dual-layer plagiarism check (semantic + text), AI cliche detection with sentence uniformity scoring, and per-client brand safety guardrails**

## Performance

- **Duration:** 13 min
- **Started:** 2026-02-27T16:14:30Z
- **Completed:** 2026-02-27T16:28:27Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Quality gate pipeline executing six gates in locked order with auto-fix-once retry semantics -- on first failure Sophia attempts a fix; on second failure the draft is rejected
- Sensitivity gate with industry-calibrated thresholds (healthcare/childcare/education industries get stricter checks) and sensitive event overlap detection
- Dual-layer plagiarism detection: semantic similarity via LanceDB (threshold 0.85) plus text-level overlap via difflib SequenceMatcher (threshold 0.60)
- AI pattern detection with 17 cliche regex patterns and sentence structure uniformity scoring (coefficient of variation < 0.3 flags unnatural uniformity)
- Quality gate integration in generate_content_batch: rejected drafts excluded from approval queue but persisted for learning; all-rejected batches raise ContentGenerationError
- Gate statistics and systemic issue detection: >30% failure rate per gate triggers specific recommendations

## Task Commits

Each task was committed atomically:

1. **Task 1: Quality gate pipeline orchestration and individual gate implementations** - `6427f16` (feat)
2. **Task 2: Integrate quality gates into generation service and add gate tracking** - `66a6c10` (feat)

## Files Created/Modified
- `backend/src/sophia/content/quality_gates.py` - Sequential gate pipeline with six gates, auto-fix-once, GateStatus/GateResult/QualityReport types
- `backend/src/sophia/content/service.py` - Gate integration in generate_content_batch, track_gate_failure(), check_systemic_gate_issues(), get_gate_statistics()
- `backend/tests/test_quality_gates.py` - 41 tests covering pipeline orchestration, all six gates, auto-fix, integration, and tracking

## Decisions Made
- **Gate dispatch table pattern:** `_GATE_FUNCTIONS` dict maps gate names to callable functions, enabling easy mock/patching in tests and future extensibility.
- **Auto-fix returns None for voice alignment:** Voice drift requires nuanced LLM rewriting that cannot be done deterministically. Other gates have heuristic fixes (remove cliches, remove superlatives, append differentiating text).
- **17 AI cliche regex patterns:** Compiled from research -- "dive in", "game-changer", "leverage", "synergy", "holistically", "transformative", "empowering", "navigating the", "landscape", "journey", "delve", "fostering", etc.
- **CV < 0.3 for sentence uniformity:** Coefficient of variation below 0.3 indicates suspiciously uniform sentence structure (human writing typically > 0.4).
- **Gate stats from gate_report JSON:** Rather than a separate tracking table, gate statistics are computed by querying ContentDraft.gate_report across recent drafts. Simpler schema, data already exists.
- **Rejected drafts persisted for learning:** Operator never sees rejected drafts in the approval queue, but they remain in the database for pattern analysis and improvement.

## Deviations from Plan

None - plan executed exactly as written. All six gates implemented as specified, auto-fix-once semantics match the locked decision, cold start bypass at <5 approved posts, dual-layer plagiarism check, and systemic issue detection at >30% threshold.

## Issues Encountered
None - plan executed cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Quality gate pipeline complete, ready for regeneration flow (03-03)
- Gate results stored on ContentDraft.gate_report for operator visibility in approval workflow (Phase 4)
- Systemic issue detection available for operator dashboard integration
- Auto-fix patterns extensible -- swap deterministic heuristics for LLM-based fixes when Claude Code integration is wired

## Self-Check: PASSED

All files verified present. Both task commits (6427f16, 66a6c10) verified in git log. 83 tests passing (41 quality gate + 42 content generation).

---
*Phase: 03-content-generation-quality-gates*
*Completed: 2026-02-27*
