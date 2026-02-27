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

- [ ] **RSRCH-01**: Sophia can research current conditions per client: local news, trends, competitive activity, community discussions (FR9)
- [ ] **RSRCH-02**: Sophia can scope research to each client's defined market scope (FR10)
- [ ] **RSRCH-03**: Sophia can monitor competitor social media and identify strategic opportunities or threats (FR11)
- [x] **RSRCH-04**: Sophia can build progressive six-domain intelligence profiles per client with completeness tracking (FR12)
- [ ] **RSRCH-05**: Sophia can detect platform algorithm changes by identifying uniform engagement shifts across portfolio (FR13)
- [ ] **RSRCH-06**: Sophia can generate diagnostic reports when client metrics plateau (FR14)
- [x] **RSRCH-07**: Sophia can retain anonymized ICP intelligence as institutional knowledge across engagements (FR15)
- [ ] **RSRCH-08**: Sophia can build platform-specific intelligence profiles categorized as "required to play" vs "sufficient to win" (FR62)
- [ ] **RSRCH-09**: Sophia can analyze algorithm shifts and proactively adapt content strategies across affected clients (FR63)

### Content Generation & Voice

- [ ] **CONT-01**: Sophia can generate platform-appropriate content drafts grounded in research + intelligence + voice profile (FR16)
- [ ] **CONT-02**: Sophia can match each client's authentic voice from approved content history and voice profile (FR17)
- [ ] **CONT-03**: Sophia can generate 2-5 content options per client for operator selection (FR18)
- [ ] **CONT-04**: Sophia can detect voice drift before content reaches approval queue (FR19)
- [ ] **CONT-05**: Operator can regenerate content with specific guidance (FR20)
- [ ] **CONT-06**: Sophia can adapt content format based on performance data (FR21)
- [ ] **CONT-07**: Sophia can apply pre-publish quality gates: research grounding, sensitivity, voice alignment, plagiarism, AI pattern detection (FR22)
- [ ] **CONT-08**: Sophia can tag content with AI-assisted labeling when mandated by platforms (FR23)
- [ ] **CONT-09**: Operator can initiate interactive voice calibration sessions through web interface (FR64)

### Approval & Publishing

- [ ] **APPR-01**: Operator can review, approve, edit, or reject content through CLI (Sprint 0), web app, or Telegram (Sprint 1) (FR24)
- [ ] **APPR-02**: Operator can approve content for automated publishing or manual copy-paste posting (FR25)
- [ ] **APPR-03**: Sophia can publish approved content to Facebook and Instagram via MCP (FR26)
- [ ] **APPR-04**: Sophia can schedule posts respecting cadence, timing, and rate limits (FR27)
- [ ] **APPR-05**: Approval state is consistent across all interfaces in real time (FR28)
- [ ] **APPR-06**: Sophia never publishes content without explicit human approval (FR29)
- [ ] **APPR-07**: Operator can use browser-based voice input via Web Speech API (FR65)

### Performance & Analytics

- [ ] **ANLY-01**: Sophia can pull engagement data from platform APIs into the database (FR30)
- [ ] **ANLY-02**: Sophia can track per-client KPIs weekly (FR31)
- [ ] **ANLY-03**: Sophia can track algorithm-independent metrics separately from algorithm-dependent metrics (FR32)
- [ ] **ANLY-04**: Sophia can measure content approval rate and edit frequency per client over time (FR33)
- [ ] **ANLY-05**: Sophia can compare audience demographics against each client's ICP (FR34)
- [ ] **ANLY-06**: Sophia can track engagement-to-inquiry conversion pathways (FR35)
- [ ] **ANLY-07**: Sophia can append UTM parameters to all published links (FR36)
- [ ] **ANLY-08**: Sophia can group posts into campaigns and track campaign-level metrics (FR36a)
- [ ] **ANLY-09**: Sophia can track CAC from social channels when client data available (FR36b)

### Evaluation Pipeline

- [ ] **EVAL-01**: Sophia can persist structured decision traces per content cycle stage (FR58)
- [ ] **EVAL-02**: Sophia can attribute performance outcomes to specific decisions (FR59)
- [ ] **EVAL-03**: Sophia can evaluate decision quality by comparing rationale against outcomes (FR60)
- [ ] **EVAL-04**: Sophia can use decision quality data to inform future content decisions (FR61)

### Learning & Self-Improvement

- [ ] **LRNG-01**: Sophia can persist all learnings to the database and load into subsequent cycles (FR37)
- [ ] **LRNG-02**: Sophia can deliver a daily standup briefing (FR38)
- [ ] **LRNG-03**: Sophia can deliver a weekly strategic briefing with cross-client patterns (FR39)
- [ ] **LRNG-04**: Sophia can extract and persist business insights from operator conversations (FR40)
- [ ] **LRNG-05**: Sophia can measure her own improvement rate across three metric categories (FR41)
- [ ] **LRNG-06**: Sophia can generate periodic intelligence reports (FR42)
- [ ] **LRNG-07**: Cross-client pattern transfer surfaced by Sophia, applied only with operator approval (FR43)

### Capability Discovery

- [ ] **CPBL-01**: Sophia can identify capability gaps during daily operations and search for solutions (FR44)
- [ ] **CPBL-02**: Sophia can evaluate discovered capabilities using scored rubric (0-5) (FR45)
- [ ] **CPBL-03**: Sophia can rank and present capability proposals with clear rationale (FR46)
- [ ] **CPBL-04**: Operator can approve or reject any proposed installation (FR47)
- [ ] **CPBL-05**: Sophia can maintain a registry of installed capabilities (FR48)

### Quality & Safety

- [x] **SAFE-01**: Sophia can enforce cross-client data isolation at aggregated pattern level (FR49)
- [x] **SAFE-02**: Sophia can encrypt all client data at rest (FR50)
- [ ] **SAFE-03**: Sophia can execute content recovery protocol for published content issues (FR51)
- [ ] **SAFE-04**: Operator can trigger content recovery for any published post (FR52)
- [ ] **SAFE-05**: Sophia can filter content for sensitivity (FR53)
- [ ] **SAFE-06**: Sophia can check generated content for originality (FR54)

### Client Communication

- [ ] **COMM-01**: Sophia can send email notifications to clients reporting performance (FR55)
- [ ] **COMM-02**: Operator can configure notification frequency and thresholds per client (FR56)
- [ ] **COMM-03**: Sophia can generate value signal communications highlighting wins (FR57)

## v2 Requirements

Deferred to Sprint 2 / Phase 2. Not in current roadmap.

- **VOICE-01**: Wake word detection + Whisper STT + TTS voice interface
- **CLOUD-01**: Cloud migration from local hosting
- **CLOUD-02**: Claude Code subscription → API transition
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
| Client self-serve dashboard | Managed service model — clients never touch software |
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
| RSRCH-01 | Phase 2 | Pending |
| RSRCH-02 | Phase 2 | Pending |
| RSRCH-03 | Phase 2 | Pending |
| RSRCH-04 | Phase 2 | Complete |
| RSRCH-05 | Phase 2 | Pending |
| RSRCH-06 | Phase 2 | Pending |
| RSRCH-07 | Phase 2 | Complete |
| RSRCH-08 | Phase 2 | Pending |
| RSRCH-09 | Phase 2 | Pending |
| CONT-01 | Phase 3 | Pending |
| CONT-02 | Phase 3 | Pending |
| CONT-03 | Phase 3 | Pending |
| CONT-04 | Phase 3 | Pending |
| CONT-05 | Phase 3 | Pending |
| CONT-06 | Phase 3 | Pending |
| CONT-07 | Phase 3 | Pending |
| CONT-08 | Phase 3 | Pending |
| CONT-09 | Phase 3 | Pending |
| SAFE-05 | Phase 3 | Pending |
| SAFE-06 | Phase 3 | Pending |
| APPR-01 | Phase 4 | Pending |
| APPR-02 | Phase 4 | Pending |
| APPR-03 | Phase 4 | Pending |
| APPR-04 | Phase 4 | Pending |
| APPR-05 | Phase 4 | Pending |
| APPR-06 | Phase 4 | Pending |
| APPR-07 | Phase 4 | Pending |
| SAFE-03 | Phase 4 | Pending |
| SAFE-04 | Phase 4 | Pending |
| ANLY-01 | Phase 5 | Pending |
| ANLY-02 | Phase 5 | Pending |
| ANLY-03 | Phase 5 | Pending |
| ANLY-04 | Phase 5 | Pending |
| ANLY-05 | Phase 5 | Pending |
| ANLY-06 | Phase 5 | Pending |
| ANLY-07 | Phase 5 | Pending |
| ANLY-08 | Phase 5 | Pending |
| ANLY-09 | Phase 5 | Pending |
| EVAL-01 | Phase 5 | Pending |
| EVAL-02 | Phase 5 | Pending |
| EVAL-03 | Phase 5 | Pending |
| EVAL-04 | Phase 5 | Pending |
| LRNG-01 | Phase 6 | Pending |
| LRNG-02 | Phase 6 | Pending |
| LRNG-03 | Phase 6 | Pending |
| LRNG-04 | Phase 6 | Pending |
| LRNG-05 | Phase 6 | Pending |
| LRNG-06 | Phase 6 | Pending |
| LRNG-07 | Phase 6 | Pending |
| CPBL-01 | Phase 6 | Pending |
| CPBL-02 | Phase 6 | Pending |
| CPBL-03 | Phase 6 | Pending |
| CPBL-04 | Phase 6 | Pending |
| CPBL-05 | Phase 6 | Pending |
| COMM-01 | Phase 6 | Pending |
| COMM-02 | Phase 6 | Pending |
| COMM-03 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 67 total
- Mapped to phases: 67
- Unmapped: 0 ✓

---
*Requirements defined: 2025-02-25*
*Last updated: 2025-02-25 after roadmap creation*
