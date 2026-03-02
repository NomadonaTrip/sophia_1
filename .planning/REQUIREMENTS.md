# Requirements: Sophia

**Defined:** 2025-02-25
**Core Value:** Every piece of content is informed, not invented — grounded in current research, stored client intelligence, and the client's voice profile.

## v1 Requirements

Requirements for Sprint 0 + Sprint 1. Each maps to roadmap phases.

### Client Management

- [x] **CLNT-01**: Operator can create and manage client profiles through conversational interaction with Sophia (FR1)
- [x] **CLNT-02**: Sophia can extract voice characteristics from client-provided materials into a structured voice profile with confidence scores (FR2)
- [x] **CLNT-03**: Operator can define content pillars, posting cadence, platform accounts, and guardrails per client (FR3)
- [x] **CLNT-04**: Sophia can define and store a market scope per client based on client brief (FR4)
- [x] **CLNT-05**: Operator can onboard a new client through iterative conversational refinement with mandatory profile fields validated (FR5)
- [x] **CLNT-06**: Sophia can progressively enrich client profiles from every interaction, timestamped and source-attributed (FR6)
- [x] **CLNT-07**: Operator can archive client data on offboard while retaining ICP intelligence as institutional knowledge (FR7)
- [x] **CLNT-08**: Operator can switch conversational context to any client by name, loading full profile and history (FR8)

### Research & Intelligence

- [x] **RSRCH-01**: Sophia can research current conditions per client: local news, trends, competitive activity, community discussions (FR9)
- [x] **RSRCH-02**: Sophia can scope research to each client's defined market scope (FR10)
- [x] **RSRCH-03**: Sophia can monitor competitor social media and identify strategic opportunities or threats (FR11)
- [x] **RSRCH-04**: Sophia can build progressive six-domain intelligence profiles per client with completeness tracking (FR12)
- [x] **RSRCH-05**: Sophia can detect platform algorithm changes by identifying uniform engagement shifts across portfolio (FR13)
- [x] **RSRCH-06**: Sophia can generate diagnostic reports when client metrics plateau (FR14)
- [x] **RSRCH-07**: Sophia can retain anonymized ICP intelligence as institutional knowledge across engagements (FR15)
- [x] **RSRCH-08**: Sophia can build platform-specific intelligence profiles categorized as "required to play" vs "sufficient to win" (FR62)
- [x] **RSRCH-09**: Sophia can analyze algorithm shifts and proactively adapt content strategies across affected clients (FR63)

### Content Generation & Voice

- [x] **CONT-01**: Sophia can generate platform-appropriate content drafts grounded in research + intelligence + voice profile (FR16)
- [x] **CONT-02**: Sophia can match each client's authentic voice from approved content history and voice profile (FR17)
- [x] **CONT-03**: Sophia can generate 2-5 content options per client for operator selection (FR18)
- [x] **CONT-04**: Sophia can detect voice drift before content reaches approval queue (FR19)
- [x] **CONT-05**: Operator can regenerate content with specific guidance (FR20)
- [x] **CONT-06**: Sophia can adapt content format based on performance data (FR21)
- [x] **CONT-07**: Sophia can apply pre-publish quality gates: research grounding, sensitivity, voice alignment, plagiarism, AI pattern detection (FR22)
- [x] **CONT-08**: Sophia can tag content with AI-assisted labeling when mandated by platforms (FR23)
- [x] **CONT-09**: Operator can initiate interactive voice calibration sessions through web interface (FR64)

### Approval & Publishing

- [x] **APPR-01**: Operator can review, approve, edit, or reject content through CLI (Sprint 0), web app, or Telegram (Sprint 1) (FR24)
- [x] **APPR-02**: Operator can approve content for automated publishing or manual copy-paste posting (FR25)
- [x] **APPR-03**: Sophia can publish approved content to Facebook and Instagram via MCP (FR26)
- [x] **APPR-04**: Sophia can schedule posts respecting cadence, timing, and rate limits (FR27)
- [x] **APPR-05**: Approval state is consistent across all interfaces in real time (FR28)
- [x] **APPR-06**: Sophia never publishes content without explicit human approval (FR29)
- [x] **APPR-07**: Operator can use browser-based voice input via Web Speech API (FR65)

### Performance & Analytics

- [x] **ANLY-01**: Sophia can pull engagement data from platform APIs into the database (FR30)
- [x] **ANLY-02**: Sophia can track per-client KPIs weekly (FR31)
- [x] **ANLY-03**: Sophia can track algorithm-independent metrics separately from algorithm-dependent metrics (FR32)
- [x] **ANLY-04**: Sophia can measure content approval rate and edit frequency per client over time (FR33)
- [x] **ANLY-05**: Sophia can compare audience demographics against each client's ICP (FR34)
- [x] **ANLY-06**: Sophia can track engagement-to-inquiry conversion pathways (FR35)
- [x] **ANLY-07**: Sophia can append UTM parameters to all published links (FR36)
- [x] **ANLY-08**: Sophia can group posts into campaigns and track campaign-level metrics (FR36a)
- [x] **ANLY-09**: Sophia can track CAC from social channels when client data available (FR36b)

### Evaluation Pipeline

- [x] **EVAL-01**: Sophia can persist structured decision traces per content cycle stage (FR58)
- [x] **EVAL-02**: Sophia can attribute performance outcomes to specific decisions (FR59)
- [x] **EVAL-03**: Sophia can evaluate decision quality by comparing rationale against outcomes (FR60)
- [x] **EVAL-04**: Sophia can use decision quality data to inform future content decisions (FR61)

### Learning & Self-Improvement

- [x] **LRNG-01**: Sophia can persist all learnings to the database and load into subsequent cycles (FR37)
- [x] **LRNG-02**: Sophia can deliver a daily standup briefing (FR38)
- [x] **LRNG-03**: Sophia can deliver a weekly strategic briefing with cross-client patterns (FR39)
- [x] **LRNG-04**: Sophia can extract and persist business insights from operator conversations (FR40)
- [x] **LRNG-05**: Sophia can measure her own improvement rate across three metric categories (FR41)
- [x] **LRNG-06**: Sophia can generate periodic intelligence reports (FR42)
- [x] **LRNG-07**: Cross-client pattern transfer surfaced by Sophia, applied only with operator approval (FR43)

### Capability Discovery

- [x] **CPBL-01**: Sophia can identify capability gaps during daily operations and search for solutions (FR44)
- [x] **CPBL-02**: Sophia can evaluate discovered capabilities using scored rubric (0-5) (FR45)
- [x] **CPBL-03**: Sophia can rank and present capability proposals with clear rationale (FR46)
- [x] **CPBL-04**: Operator can approve or reject any proposed installation (FR47)
- [x] **CPBL-05**: Sophia can maintain a registry of installed capabilities (FR48)

### Quality & Safety

- [x] **SAFE-01**: Sophia can enforce cross-client data isolation at aggregated pattern level (FR49)
- [x] **SAFE-02**: Sophia can encrypt all client data at rest (FR50)
- [x] **SAFE-03**: Sophia can execute content recovery protocol for published content issues (FR51)
- [x] **SAFE-04**: Operator can trigger content recovery for any published post (FR52)
- [x] **SAFE-05**: Sophia can filter content for sensitivity (FR53)
- [x] **SAFE-06**: Sophia can check generated content for originality (FR54)

### Client Communication

- [x] **COMM-01**: Sophia can send email notifications to clients reporting performance (FR55)
- [x] **COMM-02**: Operator can configure notification frequency and thresholds per client (FR56)
- [x] **COMM-03**: Sophia can generate value signal communications highlighting wins (FR57)

### Agentic Orchestration

- [x] **ORCH-01**: Sophia runs a daily autonomous ReAct cycle per client via cron-scheduled Editor Agent (FR66)
- [x] **ORCH-02**: Editor Agent observes client state (posting history, engagement, competitor activity, research freshness) before deciding actions (FR67)
- [x] **ORCH-03**: Editor Agent sequences research, generation, quality judgment, and approval/rejection for each client (FR68)
- [x] **ORCH-04**: Editor Agent auto-approves high-confidence content without operator intervention (FR69)
- [x] **ORCH-05**: Editor Agent flags low-confidence or risky content for operator review with explanation (FR70)
- [x] **ORCH-06**: Persistent specialist subagents accumulate client-specific context across cycles (FR71)
- [x] **ORCH-07**: Tiered skill governance: safe skills auto-acquire, risky skills require operator approval (FR72)
- [x] **ORCH-08**: Chat input bar wired to real backend with context-aware routing to Editor Agent (FR73)
- [x] **ORCH-09**: Operator time reduced to <=15 min/client/day through auto-approval and exception-only briefings (FR74)
- [x] **ORCH-10**: Full cycle audit trail with structured decision traces per stage (FR75)

## v2 Requirements

Deferred to Sprint 2 / Phase 2. Not in current roadmap.

- **VOICE-01**: Wake word detection + Whisper STT + TTS voice interface
- **CLOUD-01**: Cloud migration from local hosting
- **CLOUD-02**: Claude Code subscription -> API transition
- **PLAT-01**: LinkedIn publishing integration
- **PLAT-02**: Google Business Profile integration
- **PLAT-03**: TikTok integration
- **PLAT-04**: Automated Twitter/X + blog publishing (upgrading from manual)
- **ENGAGE-01**: Engagement management (comment/DM responses)
- **CRM-01**: Multi-touch revenue attribution with CRM integration
- **SCALE-01**: Multi-operator support

## Out of Scope

| Feature | Reason |
|---------|--------|
| Client self-serve dashboard | Managed service model -- clients never touch software |
| Real-time chat / DM management | Phase 2, high complexity and liability |
| AI image/video generation | Sophia describes visuals; generation is a separate step |
| Mobile native app | Web-first, mobile later |
| Template / content marketplace | Antithetical to research-first rule |
| HTTPS/TLS | Localhost only until Sprint 2 cloud migration |
| Rate limiting | Single operator on localhost |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLNT-01 | Phase 1 | Complete |
| CLNT-02 | Phase 1 | Complete |
| CLNT-03 | Phase 1 | Complete |
| CLNT-04 | Phase 1 | Complete |
| CLNT-05 | Phase 1 | Complete |
| CLNT-06 | Phase 1 | Complete |
| CLNT-07 | Phase 1 | Complete |
| CLNT-08 | Phase 1 | Complete |
| SAFE-01 | Phase 1 | Complete |
| SAFE-02 | Phase 1 | Complete |
| RSRCH-01 | Phase 2 | Complete |
| RSRCH-02 | Phase 2 | Complete |
| RSRCH-03 | Phase 2 | Complete |
| RSRCH-04 | Phase 2 | Complete |
| RSRCH-05 | Phase 2 | Complete |
| RSRCH-06 | Phase 2 | Complete |
| RSRCH-07 | Phase 2 | Complete |
| RSRCH-08 | Phase 2 | Complete |
| RSRCH-09 | Phase 2 | Complete |
| CONT-01 | Phase 3 | Complete |
| CONT-02 | Phase 3 | Complete |
| CONT-03 | Phase 3 | Complete |
| CONT-04 | Phase 3 | Complete |
| CONT-05 | Phase 3 | Complete |
| CONT-06 | Phase 3 | Complete |
| CONT-07 | Phase 3 | Complete |
| CONT-08 | Phase 3 | Complete |
| CONT-09 | Phase 3 | Complete |
| SAFE-05 | Phase 3 | Complete |
| SAFE-06 | Phase 3 | Complete |
| APPR-01 | Phase 4 | Complete |
| APPR-02 | Phase 4 | Complete |
| APPR-03 | Phase 4 | Complete |
| APPR-04 | Phase 4 | Complete |
| APPR-05 | Phase 4 | Complete |
| APPR-06 | Phase 4 | Complete |
| APPR-07 | Phase 4 | Complete |
| SAFE-03 | Phase 4 | Complete |
| SAFE-04 | Phase 4 | Complete |
| ANLY-01 | Phase 5 | Complete |
| ANLY-02 | Phase 5 | Complete |
| ANLY-03 | Phase 5 | Complete |
| ANLY-04 | Phase 5 | Complete |
| ANLY-05 | Phase 5 | Complete |
| ANLY-06 | Phase 5 | Complete |
| ANLY-07 | Phase 5 | Complete |
| ANLY-08 | Phase 5 | Complete |
| ANLY-09 | Phase 5 | Complete |
| EVAL-01 | Phase 5 | Complete |
| EVAL-02 | Phase 5 | Complete |
| EVAL-03 | Phase 5 | Complete |
| EVAL-04 | Phase 5 | Complete |
| LRNG-01 | Phase 6 | Complete |
| LRNG-02 | Phase 6 | Complete |
| LRNG-03 | Phase 6 | Complete |
| LRNG-04 | Phase 6 | Complete |
| LRNG-05 | Phase 6 | Complete |
| LRNG-06 | Phase 6 | Complete |
| LRNG-07 | Phase 6 | Complete |
| CPBL-01 | Phase 6 | Complete |
| CPBL-02 | Phase 6 | Complete |
| CPBL-03 | Phase 6 | Complete |
| CPBL-04 | Phase 6 | Complete |
| CPBL-05 | Phase 6 | Complete |
| COMM-01 | Phase 6 | Complete |
| COMM-02 | Phase 6 | Complete |
| COMM-03 | Phase 6 | Complete |
| ORCH-01 | Phase 7 | Complete |
| ORCH-02 | Phase 7 | Complete |
| ORCH-03 | Phase 7 | Complete |
| ORCH-04 | Phase 7 | Complete |
| ORCH-05 | Phase 7 | Complete |
| ORCH-06 | Phase 7 | Complete |
| ORCH-07 | Phase 7 | Complete |
| ORCH-08 | Phase 7 | Complete |
| ORCH-09 | Phase 7 | Complete |
| ORCH-10 | Phase 7 | Complete |

**Coverage:**
- v1 requirements: 77 total
- Mapped to phases: 77
- Unmapped: 0

---
*Requirements defined: 2025-02-25*
*Last updated: 2026-03-02 after Phase 7 planning*
