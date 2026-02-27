# Roadmap: Sophia

## Overview

Sophia delivers research-driven social media content management as a managed service. The roadmap moves from data foundation through the full daily cycle (research, generate, approve, publish, analyze, learn) to autonomous evolution. Each phase delivers a complete, verifiable capability. Sprint 0 proves the loop for Orban Forest (single client, CLI, manual posting). Sprint 1 scales to paying clients (multi-client, web app + Telegram, automated publishing).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Client Foundation & Data Security** - Client profiles, voice extraction, conversational onboarding, encrypted storage, data isolation
- [ ] **Phase 2: Research & Semantic Intelligence** - Market-scoped research engine, competitor monitoring, progressive intelligence profiles, platform intelligence
- [ ] **Phase 3: Content Generation & Quality Gates** - Research-grounded content drafts, voice matching, drift detection, quality gates, sensitivity filtering, originality checking
- [ ] **Phase 4: Approval, Publishing & Recovery** - CLI/web/Telegram approval, automated Facebook+Instagram publishing, scheduling, content recovery
- [ ] **Phase 5: Performance Analytics & Evaluation** - Engagement data collection, KPI tracking, campaign metrics, decision traces, outcome attribution
- [ ] **Phase 6: Learning, Evolution & Client Communication** - Persistent learning, briefings, capability discovery, cross-client patterns, client email notifications

## Phase Details

### Phase 1: Client Foundation & Data Security
**Goal**: Operator can onboard and manage clients through conversation, with all data encrypted and isolated
**Depends on**: Nothing (first phase)
**Requirements**: CLNT-01, CLNT-02, CLNT-03, CLNT-04, CLNT-05, CLNT-06, CLNT-07, CLNT-08, SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):
  1. Operator can create a new client (Orban Forest) through conversational interaction and all mandatory profile fields are validated
  2. Sophia extracts voice characteristics from provided materials into a structured voice profile with confidence scores
  3. Operator can switch context between clients by name and see the full profile and history loaded
  4. All client data is encrypted at rest via SQLCipher and cross-client data isolation is enforced at the aggregated pattern level
  5. Operator can archive a client and institutional ICP knowledge is retained
**Plans**: 3 plans across 2 waves

Plans:
- [ ] 01-01: Database Foundation & Configuration (Wave 1) [SAFE-02, SAFE-01, CLNT-01..08]
- [ ] 01-02: Client Management Services & Tests (Wave 2, depends on 01-01) [CLNT-01, CLNT-03..08, SAFE-01]
- [ ] 01-03: Voice Profile System & Tests (Wave 2, depends on 01-01) [CLNT-02]

### Phase 2: Research & Semantic Intelligence
**Goal**: Sophia can research current conditions scoped to each client's market and build progressive intelligence profiles
**Depends on**: Phase 1
**Requirements**: RSRCH-01, RSRCH-02, RSRCH-03, RSRCH-04, RSRCH-05, RSRCH-06, RSRCH-07, RSRCH-08, RSRCH-09
**Success Criteria** (what must be TRUE):
  1. Sophia researches current local news, trends, competitive activity, and community discussions scoped to a client's defined market
  2. Sophia builds progressive six-domain intelligence profiles per client with completeness tracking visible to operator
  3. Sophia monitors competitor social media and surfaces strategic opportunities or threats
  4. Sophia detects uniform engagement shifts across portfolio that signal platform algorithm changes and adapts content strategies
  5. Sophia generates diagnostic reports when client metrics plateau and retains anonymized ICP intelligence across engagements
**Plans**: 3 plans across 2 waves

Plans:
- [ ] 02-01: Semantic Search Infrastructure & Research Models (Wave 1) [RSRCH-04, RSRCH-07]
- [ ] 02-02: Research Engine & Competitor Monitoring (Wave 2, depends on 02-01) [RSRCH-01, RSRCH-02, RSRCH-03]
- [ ] 02-03: Algorithm Detection, Diagnostics & Platform Intelligence (Wave 2, depends on 02-01) [RSRCH-05, RSRCH-06, RSRCH-07, RSRCH-08, RSRCH-09]

### Phase 3: Content Generation & Quality Gates
**Goal**: Sophia generates research-grounded, voice-matched content drafts that pass all quality gates before reaching the approval queue
**Depends on**: Phase 2
**Requirements**: CONT-01, CONT-02, CONT-03, CONT-04, CONT-05, CONT-06, CONT-07, CONT-08, CONT-09, SAFE-05, SAFE-06
**Success Criteria** (what must be TRUE):
  1. Sophia generates 2-5 platform-appropriate content options per client, each grounded in current research, client intelligence, and voice profile
  2. Sophia matches each client's voice from approved content history and detects drift before content reaches the approval queue
  3. Operator can regenerate content with specific guidance and Sophia adapts format based on performance data
  4. All content passes pre-publish quality gates (research grounding, sensitivity filtering, voice alignment, plagiarism/originality, AI pattern detection) before entering the approval queue
  5. Content is tagged with AI-assisted labeling when mandated by platforms
**Plans**: 4 plans across 3 waves

Plans:
- [ ] 03-01: Content Generation Core & Voice Alignment (Wave 1) [CONT-01, CONT-02, CONT-03, CONT-04]
- [ ] 03-02: Quality Gate Pipeline (Wave 2, depends on 03-01) [CONT-07, SAFE-05, SAFE-06]
- [ ] 03-03: Regeneration, Calibration & Format Adaptation (Wave 3, depends on 03-01, 03-02) [CONT-05, CONT-06, CONT-08, CONT-09]
- [ ] 03-04: Gap Closure - Wire AI Label into Content Pipeline (Wave 1, gap closure) [CONT-08]

### Phase 4: Approval, Publishing & Recovery
**Goal**: Operator can review and approve content through multiple interfaces, and approved content publishes automatically to Facebook and Instagram
**Depends on**: Phase 3
**Requirements**: APPR-01, APPR-02, APPR-03, APPR-04, APPR-05, APPR-06, APPR-07, SAFE-03, SAFE-04
**Success Criteria** (what must be TRUE):
  1. Operator can review, approve, edit, or reject content through CLI (Sprint 0), web app, and Telegram (Sprint 1) with approval state consistent across all interfaces
  2. Sophia publishes approved content to Facebook and Instagram via MCP, respecting cadence, timing, and rate limits
  3. Sophia never publishes content without explicit human approval
  4. Operator can trigger content recovery for any published post and Sophia executes the recovery protocol
  5. Operator can use browser-based voice input via Web Speech API in the web interface
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Performance Analytics & Evaluation
**Goal**: Sophia tracks engagement metrics, evaluates content performance against KPIs, and builds a decision quality feedback loop
**Depends on**: Phase 4
**Requirements**: ANLY-01, ANLY-02, ANLY-03, ANLY-04, ANLY-05, ANLY-06, ANLY-07, ANLY-08, ANLY-09, EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. Sophia pulls engagement data from platform APIs and tracks weekly per-client KPIs with algorithm-independent metrics tracked separately
  2. Sophia measures content approval rate, edit frequency, audience demographics vs ICP, and engagement-to-inquiry conversion pathways per client
  3. Sophia appends UTM parameters to published links, groups posts into campaigns, and tracks campaign-level and CAC metrics
  4. Sophia persists structured decision traces per content cycle stage and attributes performance outcomes to specific decisions
  5. Sophia evaluates decision quality (predicted vs actual outcomes) and feeds decision quality data into future content decisions
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

### Phase 6: Learning, Evolution & Client Communication
**Goal**: Sophia compounds learnings across cycles, discovers new capabilities, and communicates value to clients
**Depends on**: Phase 5
**Requirements**: LRNG-01, LRNG-02, LRNG-03, LRNG-04, LRNG-05, LRNG-06, LRNG-07, CPBL-01, CPBL-02, CPBL-03, CPBL-04, CPBL-05, COMM-01, COMM-02, COMM-03
**Success Criteria** (what must be TRUE):
  1. Sophia persists all learnings to the database and loads them into subsequent cycles, with daily standup and weekly strategic briefings delivered to operator
  2. Sophia extracts business insights from operator conversations, measures her own improvement rate, and generates periodic intelligence reports
  3. Sophia identifies capability gaps during daily operations, evaluates discovered solutions on a scored rubric, and presents ranked proposals for operator approval
  4. Sophia transfers cross-client patterns only with operator approval and maintains a registry of installed capabilities
  5. Sophia sends email performance notifications to clients with configurable frequency, and generates value signal communications highlighting wins
**Plans**: 3 plans across 2 waves

Plans:
- [ ] 06-01: Learning Persistence, Scheduling & Briefings (Wave 1) [LRNG-01..07]
- [ ] 06-02: Capability Discovery & Registry (Wave 1) [CPBL-01..05]
- [ ] 06-03: Client Email Notifications & Value Signals (Wave 2, depends on 06-01) [COMM-01..03]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Client Foundation & Data Security | 0/3 | Not started | - |
| 2. Research & Semantic Intelligence | 0/3 | Not started | - |
| 3. Content Generation & Quality Gates | 0/4 | Not started | - |
| 4. Approval, Publishing & Recovery | 0/3 | Not started | - |
| 5. Performance Analytics & Evaluation | 0/3 | Not started | - |
| 6. Learning, Evolution & Client Communication | 0/3 | Not started | - |
