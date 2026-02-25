# Sophia

## What This Is

Sophia is an AI agent built on Claude Code that delivers research-driven social media content management as a managed service. She runs a daily ReAct cycle per client — observe, research, generate, approve, publish, monitor, analyze, signal, learn, improve — bringing agency-level social media intelligence to small businesses at SMB pricing ($500–$1,500/month). Operated by Tayo (Orban Forest founder) for small businesses in Southern Ontario who can't afford traditional marketing agencies.

## Core Value

Every piece of content is informed, not invented. Sophia never generates content without first grounding it in (1) current research, (2) stored client intelligence, and (3) the client's voice profile — this research-first rule is the non-negotiable differentiator that separates Sophia from every other AI content tool.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. Sprint 0 + Sprint 1. -->

**Client Management & Onboarding**
- [ ] Operator can create and manage client profiles through conversational interaction
- [ ] Sophia extracts voice characteristics from client-provided materials into structured voice profiles
- [ ] Operator can define content pillars, posting cadence, platform accounts, and guardrails per client
- [ ] Market scope per client (hyperlocal, regional, national, global)
- [ ] Iterative conversational onboarding with mandatory profile fields
- [ ] Progressive profile enrichment from every interaction (timestamped, source-attributed)
- [ ] Client offboarding with institutional knowledge retention
- [ ] Conversational context switching by client name

**Research & Intelligence**
- [ ] Research current conditions per client (local news, trends, competitive activity, community discussions)
- [ ] Research scoped to each client's defined market scope
- [ ] Competitor social media monitoring with opportunity/threat identification
- [ ] Progressive six-domain intelligence profiles per client (business, industry, competitors, customers, product/service offer, sales process)
- [ ] Platform algorithm change detection across portfolio
- [ ] Proactive diagnostic reports when metrics plateau
- [ ] Anonymized ICP intelligence retained as institutional knowledge
- [ ] Platform-specific intelligence profiles ("required to play" vs "sufficient to win")
- [ ] Proactive strategy adaptation when algorithm changes detected

**Content Generation & Voice**
- [ ] Platform-appropriate content drafts (Facebook, Instagram, Twitter/X, blog) grounded in research + intelligence + voice
- [ ] Voice matching from approved content history and voice profile
- [ ] 2-5 content options per client per cycle
- [ ] Voice drift detection before content reaches approval queue
- [ ] Regeneration with operator-specific guidance
- [ ] Format adaptation based on performance data
- [ ] Pre-publish quality gates (research grounding, sensitivity, voice alignment, plagiarism, AI pattern detection)
- [ ] AI-assisted content labeling for platform compliance
- [ ] Interactive voice calibration sessions (Sprint 1 web app)

**Approval & Publishing**
- [ ] CLI approval workflow (Sprint 0)
- [ ] Web app + Telegram approval (Sprint 1)
- [ ] Automated publishing to Facebook + Instagram via MCP (Sprint 1)
- [ ] Scheduling respecting cadence, timing, and rate limits
- [ ] Real-time approval state sync across all interfaces
- [ ] Human approval mandatory before any publish
- [ ] Browser-based voice input via Web Speech API (Sprint 1)

**Performance & Analytics**
- [ ] Engagement data pull from platform APIs
- [ ] Weekly per-client KPIs (engagement rate, save rate, CTR, audience alignment, share of voice, inbound enquiries)
- [ ] Algorithm-independent metrics tracked separately
- [ ] Content approval rate and edit frequency tracking
- [ ] Audience demographic comparison against ICP
- [ ] Engagement-to-inquiry conversion pathway tracking
- [ ] UTM parameter appending to all published links
- [ ] Campaign-level metrics (multi-post grouping)
- [ ] CAC tracking when client data available

**Evaluation Pipeline**
- [ ] Structured decision traces per content cycle stage
- [ ] Performance outcome attribution to specific decisions
- [ ] Decision quality scoring (predicted vs actual outcomes)
- [ ] Decision quality data feeding future content decisions

**Learning & Self-Improvement**
- [ ] Persist all learnings to database (approvals, edits, rejections, performance signals)
- [ ] Daily standup briefing (results, priorities, anomalies, strategic insights)
- [ ] Weekly strategic briefing (cross-client patterns, improvement opportunities)
- [ ] Business insight extraction from operator conversations
- [ ] Self-improvement rate measurement (operational, intelligence depth, adaptation metrics)
- [ ] Periodic intelligence reports (topic resonance, competitor trends, customer questions)
- [ ] Cross-client pattern transfer with operator approval

**Capability Discovery**
- [ ] Gap identification during daily operations
- [ ] Search across MCP registries, GitHub repos, Claude Code skill directories
- [ ] Scored evaluation rubric (0-5: relevance, quality, security, fit)
- [ ] Ranked proposal presentation with clear rationale
- [ ] HITL approval gate for all installations
- [ ] Installed capability registry

**Quality, Safety & Compliance**
- [ ] Cross-client data isolation (aggregated patterns only, never client-specific data)
- [ ] All client data encrypted at rest (SQLCipher)
- [ ] Content recovery protocol for published content issues
- [ ] Sensitivity filtering (local news, controversies, cultural/religious observances)
- [ ] Originality checking (no self-plagiarism, cross-client copying, AI patterns)

**Client Communication (Sprint 1)**
- [ ] Email performance notifications to clients
- [ ] Configurable notification frequency and thresholds per client
- [ ] Value signal communications highlighting wins

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Voice interface (wake word + Whisper + TTS) — Sprint 2, after MVP validated
- Cloud migration — Sprint 2, when approaching 20-client local ceiling
- LinkedIn, Google Business Profile, TikTok — Phase 2 platform expansion
- Engagement management (responding to comments/DMs) — Phase 2
- Multi-touch revenue attribution with CRM integration — Phase 2
- Multi-operator support — Phase 2
- Staff-as-content-source workflow — Phase 2
- Mobile app — Web-first, mobile later
- Real-time chat — High complexity, not core to community value
- Video/image generation pipeline — Sophia describes visuals, generation is a separate step
- HTTPS/TLS — Deferred to Sprint 2 cloud migration (localhost only)
- Rate limiting — Deferred to cloud migration (single operator on localhost)

## Context

**Existing Planning Artifacts (BMAD Framework):**
- Full PRD with 67 FRs and 33 NFRs at `_bmad-output/planning-artifacts/prd/`
- UX Design Specification (Midnight Sage design system) at `_bmad-output/planning-artifacts/ux-design-specification/`
- Architecture (project structure, decisions, implementation patterns) at `_bmad-output/planning-artifacts/architecture/`
- 8 Epics with FR mappings at `_bmad-output/planning-artifacts/epics/`

**Sprint Structure:**
- Sprint 0: Prove the full loop for Orban Forest (single client, CLI approval, manual posting, full-strength intelligence)
- Sprint 1: Scale to paying clients (multi-client, web app + Telegram approval, automated Facebook/Instagram publishing)

**Orban Forest (Test Client):**
- Starting fresh — no existing content library for voice profiling
- Voice profile will be built from competitor analysis, industry research, and onboarding conversation
- Orban Forest is Tayo's own company — dogfooding means no external dependency for Sprint 0

**MCP Server Discovery:**
- Specific MCP servers for research (Google Trends, Reddit, web scraping, competitive monitoring) to be discovered and evaluated during build
- GSD research phase should identify best available MCP servers for each capability

**Priority Signal:**
- Research quality is the proof point — the research-first rule is what separates Sophia from every other AI content tool
- Full loop speed matters, but not at the cost of dumbing down research

## Constraints

- **Hosting**: Local RTX 3080 machine (WSL2 Linux), all data on-premises. Database on ext4 (`/home/tayo/sophia/data/`), code on NTFS (`/mnt/e/`)
- **VRAM**: 8GB total, 4GB headroom, sequential model loading for BGE-M3
- **Scale ceiling**: 20 clients on local hardware. Cloud migration designed in Sprint 2
- **Operator model**: Solo operator (Tayo) managing all clients. Target ≤15 min/client/day at maturity
- **Revenue funding**: Claude Code subscription-funded (not API). API transition planned for Sprint 2
- **Platforms**: Facebook + Instagram automated (Sprint 1). Twitter/X + blog content generated but published manually by operator

## Key Decisions

<!-- Decisions that constrain future work. From BMAD planning phase. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude Code as reasoning engine (not CRUD-with-AI) | Agent-first architecture — Sophia IS Claude Code, not a web app that calls an API | — Pending |
| SQLite/SQLCipher + WAL mode | Single source of truth, encryption at rest, async via aiosqlite. PostgreSQL migration path via SQLAlchemy | — Pending |
| LanceDB + BGE-M3 for semantic intelligence | GPU-accelerated vector search, local embedding (no API dependency), hybrid search. ChromaDB as documented fallback | — Pending |
| FastAPI + React (Vite, shadcn/ui, TanStack Query) | Standard modern Python/JS stack. Midnight Sage design system from UX spec | — Pending |
| uv (backend) + pnpm (frontend) | Fast package management, lockfile-based reproducibility | — Pending |
| CLI-first for Sprint 0 | Prove intelligence before building UI. Web app comes in Sprint 1 | — Pending |
| MCP servers for platform APIs | Abstraction layer for social platform integrations. Specific servers TBD during build | — Pending |
| Manual scaffolding (no starter template) | Full control over project structure per architecture spec | — Pending |
| Research-first rule as invariant | No content generated without current research + client intelligence + voice profile. Non-negotiable | — Pending |
| Tech decisions mostly locked | Core stack from BMAD artifacts honored. Minor adjustments allowed during implementation | — Pending |

---
*Last updated: 2025-02-25 after initialization*
