---
phase: 05-performance-analytics-evaluation
verified: 2026-02-28T15:10:00Z
status: passed
score: 13/13 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 12/13
  gaps_closed:
    - "UTM parameters are appended to any URLs in post copy before publishing (ANLY-07)"
  gaps_remaining: []
  regressions: []
---

# Phase 5: Performance Analytics & Evaluation Verification Report

**Phase Goal:** Sophia tracks engagement metrics, evaluates content performance against KPIs, and builds a decision quality feedback loop
**Verified:** 2026-02-28T15:10:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure via Plan 05-04

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Raw engagement metrics can be pulled from Meta Graph API and persisted per client per post | VERIFIED | `collector.py` implements `pull_client_metrics` with httpx.AsyncClient; persists EngagementMetric rows; 21 collector tests pass |
| 2 | Each metric is tagged as algorithm-dependent or algorithm-independent at storage time | VERIFIED | `ALGO_DEPENDENT` / `ALGO_INDEPENDENT` constant sets in `models.py`; `_classify_metric()` called in `_convert_api_response_to_metrics()`; `is_algorithm_dependent` column stored per row |
| 3 | UTM parameters are appended to any URLs in post copy before publishing | VERIFIED | `inject_utm_into_copy` imported in `executor.py` (lines 27-31) with `_HAS_UTM` flag; `_derive_campaign_slug` helper at line 40; `publish_copy = inject_utm_into_copy(draft.copy, platform, campaign_slug, draft.id)` called before `_dispatch_mcp` at line 118; 3 new integration tests pass (Tests 20-22); commit 78de9e7 |
| 4 | Daily metric collection is scheduled via APScheduler and runs for all clients with valid tokens | VERIFIED | `register_daily_metric_pull()` registered in `main.py` lifespan; cron job at 6 AM operator timezone; asyncio.run() bridge for APScheduler thread; token health check on startup |
| 5 | Stale or expired API tokens produce graceful errors, not silent failures | VERIFIED | 401/403 logged and returns empty/partial list; 429 logged and returns partial; no exceptions propagated |
| 6 | Weekly KPI snapshots are computed per client from raw engagement metrics with standard and custom KPIs | VERIFIED | `compute_weekly_kpis()` in `kpi.py`; computes engagement_rate, save_rate, share_rate, reach_growth_pct, follower_growth_pct; 14 kpi tests pass |
| 7 | Approval rate, edit frequency, rejection rate, and regeneration count are tracked per client | VERIFIED | `compute_weekly_kpis()` queries `ApprovalEvent` for approval_rate, edit_frequency, rejection_rate; queries `ContentDraft.regeneration_count` |
| 8 | Comment sentiment is analyzed per post using VADER | VERIFIED | `analyze_comment_sentiment()` in `sentiment.py`; lazy imports vaderSentiment per NTFS pattern; stores avg_compound as `comment_quality_score` EngagementMetric |
| 9 | Anomaly detection flags statistically unusual engagement events | VERIFIED | `detect_metric_anomaly()` in `anomaly.py` uses MAD-based modified z-score; requires 7+ data points; high/medium severity; `detect_client_anomalies()` and `detect_portfolio_anomalies()` for portfolio |
| 10 | Audience demographics from Instagram API can be compared against client ICP personas | VERIFIED | `pull_audience_demographics()` in `icp.py` (async httpx); `compare_audience_to_icp()` scores age/gender/location match per persona |
| 11 | Decision traces are captured at each content cycle stage | VERIFIED | `decision_trace.py` has `capture_decision()` for all 8 stages; wired into content/service.py, quality_gates.py, approval/service.py, and publishing/executor.py via try/except ImportError |
| 12 | Performance outcomes are attributed back to specific decisions via content_draft_id joins | VERIFIED | `attribute_outcomes()` queries EngagementMetric by content_draft_id and updates `actual_outcome` on all DecisionTrace rows for that draft |
| 13 | Decision quality scores feed back into content generation context for future cycles | VERIFIED | `get_decision_quality_context()` queries most recent DecisionQualityScore per type; returns structured dict with guidance; called from content/service.py via lazy import |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/src/sophia/analytics/models.py` | 8 ORM models with algorithm classification | VERIFIED | All 8 models: EngagementMetric, KPISnapshot, Campaign, CampaignMembership, ConversionEvent, DecisionTrace, DecisionQualityScore, IndustryBenchmark. ALGO_DEPENDENT/ALGO_INDEPENDENT constants present. |
| `backend/src/sophia/analytics/collector.py` | Meta Graph API metric puller | VERIFIED | `pull_engagement_metrics` pattern via `pull_client_metrics`; async httpx; `register_daily_metric_pull`; graceful error handling |
| `backend/src/sophia/analytics/utm.py` | UTM parameter builder | VERIFIED | `build_utm_url` and `inject_utm_into_copy` exist, substantive (9 tests pass), and are now called from `executor.py` (commit 78de9e7). Previously ORPHANED — gap is closed. |
| `backend/src/sophia/analytics/router.py` | Analytics API endpoints | VERIFIED | `analytics_router` with 9 total endpoints (5 original + 4 decision trace); registered in main.py |
| `backend/src/sophia/analytics/schemas.py` | Pydantic v2 response schemas | VERIFIED | EngagementMetricResponse, KPISnapshotResponse, CampaignResponse, ConversionEventCreate, AnalyticsSummaryResponse, DecisionTraceResponse |
| `backend/src/sophia/analytics/kpi.py` | KPI computation service | VERIFIED | `compute_weekly_kpis`, `compute_kpi_trends`, `compare_to_benchmark`, `compute_posting_time_performance` |
| `backend/src/sophia/analytics/campaigns.py` | Campaign auto-grouping | VERIFIED | `auto_group_campaigns` by content_pillar + month, `compute_campaign_metrics`, `list_campaigns` |
| `backend/src/sophia/analytics/sentiment.py` | VADER comment sentiment | VERIFIED | `analyze_comment_sentiment` with lazy VADER import; `analyze_post_sentiment` stores as EngagementMetric |
| `backend/src/sophia/analytics/anomaly.py` | MAD-based anomaly detection | VERIFIED | `detect_metric_anomaly`, `detect_client_anomalies`, `detect_portfolio_anomalies` |
| `backend/src/sophia/analytics/icp.py` | ICP audience comparison | VERIFIED | `pull_audience_demographics` (async httpx), `compare_audience_to_icp` |
| `backend/src/sophia/analytics/funnel.py` | Conversion funnel + CAC/CLV | VERIFIED | `log_conversion_event`, `compute_funnel_metrics`, `compute_cac` (returns None when no data) |
| `backend/src/sophia/analytics/briefing.py` | Morning brief + weekly briefing | VERIFIED | `generate_morning_brief` (sage/amber/coral classification), `generate_weekly_briefing`, `generate_telegram_digest` |
| `backend/src/sophia/analytics/decision_trace.py` | Decision trace pipeline | VERIFIED | `capture_decision`, `capture_generation_decisions`, `capture_gate_decision`, `capture_approval_decision`, `attribute_outcomes`, `attribute_batch`, `compute_decision_quality`, `evaluate_decision_quality_batch`, `get_decision_quality_context` |
| `frontend/src/components/analytics/MetricChart.tsx` | Recharts wrapper | VERIFIED | line/bar/radar/composed; full chat width; Midnight Sage theme |
| `frontend/src/components/analytics/KPIDashboardCard.tsx` | Compact KPI card | VERIFIED | change indicators, status dot, algo-independent highlight |
| `frontend/src/components/analytics/PortfolioAnalytics.tsx` | Portfolio grid | VERIFIED | sage/amber/coral tiles, summary row, hover anomaly detail |
| `frontend/src/components/analytics/CampaignSummary.tsx` | Campaign performance card | VERIFIED | stats row, engagement progress bar |
| `frontend/src/components/analytics/PostingHeatmap.tsx` | Posting time heatmap | VERIFIED | 24-hour grid with color intensity |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `analytics/collector.py` | `analytics/models.py` | `EngagementMetric` model for persistence | VERIFIED | `from sophia.analytics.models import ALGO_DEPENDENT, EngagementMetric` at top; `EngagementMetric(...)` created in `_convert_api_response_to_metrics` |
| `analytics/collector.py` | `sophia/config.py` | `Settings` for API tokens and timezone | VERIFIED | `from sophia.config import Settings` at top; `settings.facebook_access_token`, `settings.operator_timezone` used |
| `main.py` | `analytics/router.py` | `include_router` registration | VERIFIED | `from sophia.analytics.router import analytics_router` at line 13; `app.include_router(analytics_router)` at line 151 |
| `analytics/utm.py` | `publishing/executor.py` | UTM injection before MCP dispatch | VERIFIED | `from sophia.analytics.utm import inject_utm_into_copy` at lines 27-31 (with ImportError fallback); `publish_copy = inject_utm_into_copy(draft.copy, platform, campaign_slug, draft.id)` at line 118; `"copy": publish_copy` in dispatch dict. Previously NOT_WIRED — gap is closed in commit 78de9e7. |
| `analytics/kpi.py` | `analytics/models.py` | Queries EngagementMetric, persists KPISnapshot | VERIFIED | Both models imported at top; `db.query(EngagementMetric)` and `KPISnapshot(...)` used |
| `analytics/kpi.py` | `approval/models.py` | Queries ApprovalEvent for quality KPIs | VERIFIED | `from sophia.approval.models import ApprovalEvent` inside function; `db.query(ApprovalEvent)` with client_id filter |
| `analytics/campaigns.py` | `content/models.py` | Queries ContentDraft.content_pillar | VERIFIED | `from sophia.content.models import ContentDraft` inside function; filters by `content_pillar` |
| `analytics/icp.py` | `analytics/collector.py` | `pull_audience_demographics` | VERIFIED | `pull_audience_demographics` defined in icp.py; comparison function `compare_audience_to_icp` substantive |
| `analytics/sov.py` | `research/models.py` | CompetitorSnapshot for SOV | VERIFIED | `from sophia.research.models import Competitor, CompetitorSnapshot` at top |
| `analytics/decision_trace.py` | `analytics/models.py` | DecisionTrace and DecisionQualityScore | VERIFIED | Both imported at top; used throughout |
| `content/service.py` | `analytics/decision_trace.py` | `capture_decision` called during generation | VERIFIED | `from sophia.analytics.decision_trace import capture_generation_decisions` inside try/except ImportError block at line 250 |
| `content/quality_gates.py` | `analytics/decision_trace.py` | `capture_gate_decision` | VERIFIED | Wired at lines 162 and 191 in quality_gates.py |
| `approval/service.py` | `analytics/decision_trace.py` | `capture_approval_decision` | VERIFIED | Wired at line 91 in approval/service.py |
| `MetricChart.tsx` | `recharts` | LineChart, BarChart, RadarChart imports | VERIFIED | `from 'recharts'` at top; recharts@^3.7.0 in package.json; TypeScript compiles cleanly |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ANLY-01 | 05-01 | Pull engagement data from platform APIs into DB (FR30) | SATISFIED | `pull_client_metrics()` + `pull_all_clients_metrics()` in collector.py; 21 tests |
| ANLY-02 | 05-02 | Track per-client KPIs weekly (FR31) | SATISFIED | `compute_weekly_kpis()` + `KPISnapshot` model; 14 kpi tests |
| ANLY-03 | 05-01 | Track algorithm-independent metrics separately (FR32) | SATISFIED | `ALGO_DEPENDENT` / `ALGO_INDEPENDENT` constants; `is_algorithm_dependent` field on every EngagementMetric row |
| ANLY-04 | 05-02 | Measure content approval rate and edit frequency (FR33) | SATISFIED | `approval_rate`, `edit_frequency`, `rejection_rate`, `regeneration_count` in KPISnapshot via ApprovalEvent queries |
| ANLY-05 | 05-02 | Compare audience demographics against ICP (FR34) | SATISFIED | `pull_audience_demographics()` + `compare_audience_to_icp()` in icp.py |
| ANLY-06 | 05-02 | Track engagement-to-inquiry conversion pathways (FR35) | SATISFIED | `FUNNEL_STAGES` + `log_conversion_event()` + `compute_funnel_metrics()` in funnel.py |
| ANLY-07 | 05-01, 05-04 | Append UTM parameters to all published links (FR36) | SATISFIED | `build_utm_url` and `inject_utm_into_copy` in utm.py; wired into executor.py at lines 27-31, 114-120; `publish_copy` (not `draft.copy`) passed to `_dispatch_mcp`; 3 integration tests + 9 unit tests all pass; commit 78de9e7 |
| ANLY-08 | 05-02 | Group posts into campaigns and track campaign-level metrics (FR36a) | SATISFIED | `auto_group_campaigns()` groups by content_pillar + month; `compute_campaign_metrics()` aggregates |
| ANLY-09 | 05-02 | Track CAC from social channels when client data available (FR36b) | SATISFIED | `compute_cac()` returns None when no revenue data; computes CAC/CLV when ConversionEvents with revenue_amount exist |
| EVAL-01 | 05-03 | Persist structured decision traces per content cycle stage (FR58) | SATISFIED | `capture_decision()` for 8 stages; wired in content, quality_gates, approval, executor |
| EVAL-02 | 05-03 | Attribute performance outcomes to specific decisions (FR59) | SATISFIED | `attribute_outcomes()` joins EngagementMetric to DecisionTrace via content_draft_id; `attribute_batch()` for batch processing |
| EVAL-03 | 05-03 | Evaluate decision quality by comparing rationale against outcomes (FR60) | SATISFIED | `compute_decision_quality()` with weighted scoring per decision_type; `evaluate_decision_quality_batch()` creates DecisionQualityScore records |
| EVAL-04 | 05-03 | Use decision quality data to inform future content decisions (FR61) | SATISFIED | `get_decision_quality_context()` returns structured guidance dict; wired into content/service.py before generation |

All 13 phase requirements (ANLY-01 through ANLY-09, EVAL-01 through EVAL-04) are satisfied. No orphaned requirements detected.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `analytics/router.py` | 83 | `"detailed_kpis": {}` stub in portfolio summary | Info | Portfolio summary endpoint returns partial stub; the real computation is in `generate_morning_brief()` in briefing.py. Not a blocker — router documents intent in a comment. |
| `analytics/router.py` | 163 | `anomalies=[]` in client summary response | Info | Anomalies are intentionally computed via `detect_client_anomalies()` in briefing flow, not inline in summary. Consistent with documented design. |

No blocker anti-patterns remain. The previously identified blocker (UTM injection orphaned in executor.py) is resolved.

### Human Verification Required

None required. All automated checks are definitive.

### Re-verification Summary

**Gap closed:** ANLY-07 (UTM injection) was the sole blocker identified in the initial verification. Plan 05-04 wired `inject_utm_into_copy` from `analytics/utm.py` into `publishing/executor.py` before `_dispatch_mcp`. Specifically:

- `from sophia.analytics.utm import inject_utm_into_copy` added at executor.py lines 27-31 with `try/except ImportError` for graceful degradation
- `_derive_campaign_slug(draft)` helper at line 40 slugifies `content_pillar` with `"general"` fallback
- `publish_copy = inject_utm_into_copy(draft.copy, platform, campaign_slug, draft.id)` called at lines 116-120 before `_dispatch_mcp`
- `draft.copy` in the database is never mutated — UTM-tagged copy is publish-only
- 3 integration tests added (Tests 20-22): UTM in dispatch, no-URL passthrough, default campaign slug
- Commit 78de9e7 confirmed in git log

**Test results:** 32 tests pass (23 publishing tests including 3 new UTM tests + 9 UTM unit tests), confirmed live run in this verification session.

**No regressions detected.** All 12 previously verified truths continue to hold.

---

_Verified: 2026-02-28T15:10:00Z_
_Verifier: Claude (gsd-verifier)_
