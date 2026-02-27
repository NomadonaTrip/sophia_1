# Phase 4: Approval, Publishing & Recovery - Research

**Researched:** 2026-02-27 (forced re-research with BMAD cross-referencing)
**Domain:** Multi-interface approval workflow, social media publishing APIs, real-time state sync, chat-first web UI, Telegram bot integration, content recovery, browser voice input
**Confidence:** MEDIUM-HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fixed triage order: attention (coral) first, calibrating (amber) second, cruising (sage) third
- Three-state client status system: Cruising (sage), Calibrating (amber), Attention (coral)
- Structured hybrid morning brief: stat cards + narrative bullets, orientation in under 5 seconds
- Full session summary auto-appears when queue hits 0
- Morning session arc: Brief -> Attention -> Calibrating -> Cruising -> Session summary -> Close
- Chat-first with rich cards: conversation thread is the primary container, NOT a portfolio grid/dashboard
- Persistent health strip below nav: cruising/calibrating/attention counts + posts remaining, updates live
- Conversation topics as nav tabs: Morning Brief, Client Drill-Down, Approval Queue, Calibration, Analytics, Session Close
- Panel expansion over page routing: details expand inline, never navigate away
- Chat input always present at bottom
- Full Midnight Sage palette with Landio depth: near-black canvas (#04070d), sage green accents, radial gradient sage glows, backdrop-filter blur, atmospheric layering
- Dual typography: Inter (400-900) for data + Instrument Serif italic for Sophia's personality
- Color-as-status system: Sage = cruising, Amber = calibrating, Coral = attention. Never decorative
- Dark mode only (Midnight Sage IS the design)
- Rich preview cards (Direction E): header + quality badges + collapsible rationale + image prompt + post text + action buttons
- Quality gate badges visible on card surface: voice alignment, research grounding, sensitivity, plagiarism
- Platform mockup previews: visual preview of how post will appear on each platform
- Collapsible 'Why this?' context panel
- Per-client organization: default groups content by client
- Batch approval with individual override for cruising clients
- Drag-to-reorder: after approval, operator can rearrange timing in content calendar
- Keyboard shortcuts: Tab/arrows navigate, A approve, R reject, E edit, N next
- Mobile-responsive: desktop-first, adapts to mobile
- Sophia personality throughout: greetings, explanations, suggestions
- Activity dashboard (via tab): approval stats and history
- Content calendar (via tab): scheduled and published content
- Three rejection guidance methods: quick tags, typed feedback, voice input (all available simultaneously)
- Quick tag presets: Too Formal, Too Casual, Wrong Angle, Off-Brand, Too Long, Too Short
- Guidance applied label visible on regenerated drafts
- Auto-suggest calibration after 3+ rejections for same client in session
- Manual operator-written drafts are publishable AND voice learning samples
- Skip post is a first-class action
- Locked micro-interaction patterns (approved fade to 40% + check, rejected border pulse coral, batch 200ms stagger, regeneration slide, session summary sage glow)
- Sophia thinking indicator: sage dot pulse, text after 3 seconds
- Sophia acknowledgment: commentary only after significant actions, not individual approvals
- Error handling: network failure = amber banner + auto-retry 3x + manual retry, API failure = Sophia commentary + auto-resolution attempt
- Telegram: one message per option with inline buttons (Approve / Edit / Reject / Next), editing via reply
- CLI: functional but minimal (Sprint 0)
- Inline edit + regenerate: both paths available
- Real-time sync across all interfaces: approve on Telegram -> web app updates instantly
- Approval deadlines: nudge at 4 hours, mark stale if freshness window expires. Never auto-approve
- Approve with custom time: defaults to suggested but operator can override
- Multiple approvals per client queued with appropriate spacing
- Configurable notification preferences per channel
- Per-client default publish mode with per-post override (auto or manual)
- Silent publish after approval: no further check-ins
- Post-publish confirmation with link via Telegram + web app
- Image handling: Sophia provides image prompts only. Operator uploads image. Post doesn't publish without image
- Per-client cadence rules: X posts/week/platform, min hours between posts, preferred posting days
- Coordinated but independent cross-posting: same content, platform-specific versions, platform-optimized times. Approve once, both go out
- Automatic rate limit management: track API rate limits, space posts to stay within limits
- Publishing failure: retry 3x with backoff then alert via Telegram
- Copy-ready package for manual clients: copyable text, image prompt, hashtags, suggested time, platform formatting notes
- Global pause button: one-click pause all scheduled publishing, accessible from web + Telegram
- Content recovery protocol: delete/unpublish -> archive internally with reason -> notify operator. Full audit trail
- Recovery from any interface: web, Telegram, CLI. Two urgency levels: "Remove now" (immediate) and "Review for removal" (assess and recommend)
- Proactive post-publish monitoring: negative comment spikes, broken links, factual inaccuracies
- Offer replacement after recovery
- Voice input scope: commands for approvals, rejections, regeneration guidance. Hands-free review
- Voice confirmation: approvals and regeneration execute immediately. Rejections and recoveries require confirmation
- Voice feedback: visual only (on-screen text/toast). No TTS
- Voice activation: push-to-talk (hold mic button or press hotkey)

### Claude's Discretion
- Database schema for approval state, publishing queue, and recovery logs
- MCP integration architecture for Facebook and Instagram APIs
- Real-time sync implementation approach (WebSocket, SSE, polling)
- Telegram bot framework and conversation state management
- Platform mockup rendering approach
- Keyboard shortcut conflict resolution
- Rate limit tracking algorithm details
- Web Speech API integration specifics
- Exact client status thresholds (what approval rate = cruising, what engagement drop = attention)
- Skeleton loading layout details
- Morning brief narrative bullet content and ordering

### Deferred Ideas (OUT OF SCOPE)
- Browser TTS (Sophia speaking back) -- deferred to RTX 3080 voice interface
- Always-listen wake word activation -- deferred to full voice interface
- AI image generation -- Sophia provides prompts, does not generate images
- Per-client pause (in addition to global)
- Portfolio grid view (v3.2 visual command center paradigm)
- Voice calibration panels (side-by-side A/B/C experiments) -- belongs in Phase 3 or sub-flow
</user_constraints>

## Summary

Phase 4 is the largest and most architecturally complex phase in the Sophia project. It introduces three new user-facing surfaces (CLI approval, web app, Telegram bot), a publishing pipeline to external platform APIs, a real-time state synchronization layer, and browser-based voice input. This phase bridges the backend intelligence pipeline (Phases 1-3) with the operator experience, transforming raw content drafts into reviewed, approved, scheduled, and published social media posts.

The core technical domains span: (1) a chat-first React web application implementing the Midnight Sage design system with shadcn/ui components per the UX Design Specification, (2) a FastAPI backend serving both REST APIs and real-time events, (3) Telegram bot integration via python-telegram-bot webhooks running in the same FastAPI process, (4) Facebook and Instagram publishing via existing MCP servers (HagaiHen/facebook-mcp-server, jlbadano/ig-mcp), (5) an event-driven state synchronization system across all interfaces, and (6) Web Speech API integration for browser voice input.

The frontend does not exist yet -- it must be scaffolded from scratch. The backend already has a working FastAPI router pattern (research and content routers with placeholder DB dependencies), SQLAlchemy models for ContentDraft (with status field supporting "draft", "in_review", "approved", "rejected", "published"), and a full service layer for content generation, regeneration, quality gates, and calibration. Phase 4 extends this foundation with approval workflow services, a publishing pipeline, and new database models for publishing queue management and recovery logs.

**CRITICAL BMAD cross-reference findings:** The UX Design Specification defines 13 custom components with exact behavioral specs, a three-tier action hierarchy (Approve=sage/primary, Edit=neutral/secondary, Reject=ghost/tertiary), locked micro-interaction timings, skeleton loading patterns (sage-tinted pulse, 1.5s), progressive content loading (attention->calibrating->cruising stagger), and a Sophia thinking indicator (sage dot pulse, NOT spinner). The component-strategy.md defines an implementation roadmap (4 phases over 4 weeks) that Phase 4 plans should align with. The user-journey-flows.md defines five distinct flows (Morning Session, Client Deep-Dive, Voice Calibration, Cross-Client Insight, Content Regeneration) that map to specific component compositions.

**Primary recommendation:** Use SSE (Server-Sent Events) over WebSocket for real-time server-to-client updates. SSE is simpler, uses standard HTTP, auto-reconnects, and fits the unidirectional update pattern (server pushes approval state changes, health strip updates, publishing confirmations). Chat input uses standard REST POST. Reserve WebSocket for future Sprint 2/3 if bidirectional streaming is needed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| APPR-01 | Operator can review, approve, edit, or reject content through CLI (Sprint 0), web app, or Telegram (Sprint 1) (FR24) | CLI: simple stdin/stdout loop. Web: React chat-first UI with shadcn/ui rich cards implementing ContentItem sub-component spec (platform label, content text, voice %, sources, pillar, scheduled time) + three-tier action hierarchy (Approve=sage, Edit=neutral, Reject=ghost). Telegram: python-telegram-bot v22.6 with inline keyboards. All three call same backend approval service via state machine. UX spec mandates: approved=40% opacity fade+check, rejected=coral pulse, batch=200ms stagger (ux-consistency-patterns.md) |
| APPR-02 | Operator can approve content for automated publishing or manual copy-paste posting (FR25) | Backend approval service sets publish_mode per approval. Manual clients get copy-ready package (copyable text + image prompt + hashtags + time + platform formatting notes). Automated clients enter publishing queue. Per-client default with per-post override (CONTEXT.md locked decision) |
| APPR-03 | Sophia can publish approved content to Facebook and Instagram via MCP (FR26) | facebook-mcp-server (HagaiHen): 28 tools including post_to_facebook, post_image_to_facebook, schedule_post, delete_post. ig-mcp (jlbadano): 8 tools including publish_media. Both require access tokens + page/account IDs. Instagram deletion NOT supported in ig-mcp (listed as "future feature") |
| APPR-04 | Sophia can schedule posts respecting cadence, timing, and rate limits (FR27) | Publishing scheduler service enforces per-client cadence rules, minimum hours between posts, and API rate limits. Facebook: 200 calls/hour/user. Instagram: 25-100 posts/24hrs (conflicting sources -- use Content Publishing Limit endpoint to check). APScheduler 3.x for in-process scheduling with SQLAlchemy job store |
| APPR-05 | Approval state is consistent across all interfaces in real time (FR28) | SSE event bus broadcasts approval state changes from FastAPI. Web app subscribes via EventSource. Telegram receives push via bot.send_message on state change. CLI polls or receives notifications. TanStack Query cache invalidation on SSE event receipt for instant UI updates |
| APPR-06 | Sophia never publishes content without explicit human approval (FR29) | Enforced at publishing service level: only drafts with status="approved" enter the publishing queue. Double-check on publish execution. Audit log entry on every publish. State machine prevents draft->published transition (must go through approved) |
| APPR-07 | Operator can use browser-based voice input via Web Speech API (FR65) | SpeechRecognition interface supported in Chrome/Edge (Chromium). Push-to-talk activation. Command parsing maps speech to approval actions. Visual-only feedback (no TTS). Feature-detect and show/hide mic button based on browser support. Internet required (audio sent to cloud for transcription). UX spec: ChatInputBar mic button with sage pulse when recording (component-strategy.md) |
| SAFE-03 | Sophia can execute content recovery protocol for published content issues (FR51) | Facebook: delete_post tool via facebook-mcp-server. Instagram: deletion NOT supported in ig-mcp -- recovery for Instagram may require manual deletion with Sophia archiving internally. Internal archive with reason. Audit trail. Replacement content offer after recovery (CONTEXT.md locked decision) |
| SAFE-04 | Operator can trigger content recovery for any published post (FR52) | Recovery triggerable from web (button on published post card), Telegram (inline button), CLI (command). Two urgency levels: immediate vs review-for-removal. All interfaces call same recovery service. Event bus notifies all surfaces on recovery completion |
</phase_requirements>

## BMAD UX Specification Cross-Reference

This section captures critical UX specification requirements that Phase 4 implementation MUST comply with. Previous research did not cross-reference these sufficiently.

### Component Specifications (from component-strategy.md)

The UX spec defines 13 custom components. Phase 4 must implement these (some are Phase 4 scope, others are scaffolding for later phases):

**Phase 4 Core Components (must implement):**

| Component | Phase 4 Role | Key Specs |
|-----------|-------------|-----------|
| **HealthStrip** | Persistent status bar, always visible | Fixed below header. Cruising/calibrating/attention counts with colored `Circle` dots. Posts remaining. `role="status"`, `aria-live="polite"`. Queue-clear state shows `Check` + "Queue clear" in sage |
| **SophiaCommentary** | Sophia's strategic text in chat stream | Surface bg, sage left border (3px), subtle radial glow top-left. Header: Instrument Serif italic 16px. Variants: standard (morning brief, inline), compact (one-liner acks). `role="article"` |
| **BatchApprovalGrid** | Scannable grid for cruising-client batch approve | 2-column grid of BatchApprovalItem. "Approve All [n]" in header. `role="list"`. Partially-approved state (some faded) and fully-approved state |
| **BatchApprovalItem** | Individual item in batch grid | Client name + platform, 2-line content preview, voice %, format, scheduled time, action buttons. Approved=40% opacity+check. `role="listitem"` |
| **ChatInputBar** | Persistent bottom input | Text input + mic button + send button. Fixed bottom, backdrop blur, surface border top. Mic: `Mic` icon, sage pulse when recording, `Square` to stop. Send: `ArrowUp`, sage-filled with glow. `role="form"` |
| **QuickTagSelector** | Preset rejection feedback | "Too Formal", "Too Casual", "Wrong Angle", "Off-Brand", "Too Long", "Too Short". Rounded buttons, multiple selection. `role="group"`, `aria-pressed` toggles. `Check` prefix on selected. `Tag` icon on label |
| **ContentItem** | Content card sub-component | Platform label (uppercase, muted), content text, voice %, sources, pillar, scheduled time, action buttons. States: default, approved (faded), editing (inline active), rejected (regeneration flow). `Check`/`Pencil`/`X` icons |
| **SessionSummary** | Auto-appears when queue = 0 | Serif italic title "Session Complete". Stats: approved, edited, regenerated, calibrated, session time. Centered layout, radial glow top center. `role="status"`, `aria-live="polite"` |
| **ClientDetailPanel** | Composite panel for client drill-down | Header (name, business, status badge), metrics row (4 KPIs with trends), Sophia diagnosis, content queue. Expands inline (250ms ease-out). `Escape` to collapse. `role="region"` |

**Phase 4 Scaffolding Components (structural, minimal content):**

| Component | Phase 4 Role | Notes |
|-----------|-------------|-------|
| **ClientTile** | Compact client overview in portfolio grid | Needed for morning brief. Sparkline, engagement rate, voice match %, status left border. Click triggers deep-dive |
| **PortfolioGrid** | Grid of client tiles, auto-sorted by urgency | 5/3/2 columns at desktop/tablet/mobile. 8px gap. `role="grid"`, arrow key navigation |
| **InsightCard** | Cross-client pattern detection | Sage-tinted border, `Zap`/`Lightbulb`/`TrendingUp` icons, serif italic label, action buttons. Required for morning brief |
| **InlineChart** | Data visualization in chat stream | HorizontalBar variant only for Phase 4 MVP. Sage gradient bars. `role="img"` with `aria-label` |

**NOT in Phase 4 scope:**
- CalibrationPanel -- deferred per CONTEXT.md (voice calibration panels are Phase 3 sub-flow)
- Sparkline -- needed inside ClientTile, implement as part of ClientTile

### Three-Tier Action Hierarchy (from ux-consistency-patterns.md)

**MANDATORY across all content approval surfaces:**

| Tier | Action | Visual | Behavior | Position |
|------|--------|--------|----------|----------|
| Primary | Approve | Sage-filled button, `Check` icon, glow shadow | Single click. Item fades to 40% opacity. Count decrements | Rightmost (desktop), topmost (mobile) |
| Secondary | Edit | Surface-raised button, `Pencil` icon, subtle border | Opens inline edit or Sheet. Requires follow-up save | Left of primary |
| Tertiary | Reject | Ghost button, `X` icon, muted text color | Opens QuickTagSelector or guidance. Requires explanation | Leftmost |

Keyboard shortcuts (Sprint 1): A=approve, E=edit, R=reject, Tab/Shift+Tab=navigate items.

### Feedback & Animation Patterns (from ux-consistency-patterns.md)

**Locked timings -- implementation MUST match these exactly:**

| Action | Feedback | Timing |
|--------|----------|--------|
| Approve | Item fades to 40% opacity. Button shows `Check`. Health strip count decrements | Instant (<100ms) |
| Edit saved | Brief sage flash on item border. Button returns to default | 150ms flash |
| Reject sent | Item border pulses coral once. QuickTagSelector/guidance appears | Instant |
| Batch approve | All items fade simultaneously. Header: "All Approved" + `Check` | 200ms stagger |
| Calibration pick | Selected option gets sage border + glow. Others dim | 150ms transition |
| Regeneration complete | New draft slides in replacing old. "Guidance applied: [tags]" label | 300ms slide |
| Insight dismissed | Card fades out and collapses | 200ms fade |
| Session complete | SessionSummary animates in from center. Sage radial glow pulses once | 400ms entrance |

### Skeleton Loading (from ux-consistency-patterns.md)

- Every custom component MUST have a skeleton variant
- Surface-colored rectangles with sage-tinted pulse animation (1.5s cycle)
- Skeletons match exact layout of loaded state
- Progressive content loading: attention tiles first (immediate), calibrating (50ms delay), cruising (100ms stagger)

### Sophia Thinking Indicator (from ux-consistency-patterns.md)

- Sage dot pulse in ChatInputBar area
- NO spinner. NO "typing..." text
- For operations >3 seconds: brief text appears below dot ("Generating chart...", "Regenerating with your feedback...")
- Sophia acknowledgment commentary ONLY after significant actions (batch approvals, calibration completions, insight decisions). Individual approves get visual feedback only -- NO Sophia commentary

### Visual Design Tokens (from visual-design-foundation.md)

**Midnight Sage color system:**

| Role | Token | Value | Usage |
|------|-------|-------|-------|
| Canvas | `--midnight-950` | ~#020509 | App background base layer |
| Canvas | `--midnight-900` | ~#04070d | Primary canvas |
| Surface | `--midnight-800` | ~#0a1019 | Content cards, panels, bubbles |
| Surface raised | `--midnight-700` | ~#111a26 | Hover states, active elements |
| Sage accent | `--sage-500` | ~#4a7c59 | Primary interactive elements, approve, success |
| Sage bright | `--sage-400` | ~#5a9c6a | Hover, links |
| Sage light | `--sage-300` | ~#7ab88a | Text accent |
| Sage subtle | `--sage-200` | ~#a0d4aa | Background highlights |
| Amber | `--amber-500` | ~#c58c3c | Calibrating, warnings |
| Coral | `--coral-500` | ~#c55a5a | Attention, errors, rejections |
| Text primary | `--text-primary` | ~#e8f0ea | Warm white body text |
| Text secondary | `--text-secondary` | ~#a0b4a8 | Timestamps, metadata |
| Text muted | `--text-muted` | ~#6b8070 | Disabled, placeholders |

**Typography:**
- Data/UI: Inter (400-900), 14px body, 600 semibold headings, tabular nums for metrics
- Sophia personality: Instrument Serif italic ONLY. Reserved for commentary headers, insight labels, session titles. Self-hosted with `font-display: swap` and `<link rel="preload">`
- 14px body anchor, 1.45 line height, 4px base spacing unit

**Layout:**
- Conversation-native single column, ~720px message width, centered
- Desktop-first (morning ritual on laptop)
- Messages 8px apart, 16px between client groups, 12px card padding
- Chat input: fixed bottom, 48px height, 12px padding
- Card radius: 14px, 1px light-catching borders
- Elevation over borders (canvas -> surface -> surface raised)

### User Journey Flow Mapping (from user-journey-flows.md)

**Morning Session Flow:** Open -> Auth -> Morning Brief (PortfolioGrid + HealthStrip + SophiaCommentary) -> Attention clients (Client Deep-Dive) -> Calibrating clients (Voice Calibration) -> Cruising clients (Batch Approval Queue) -> Queue Clear -> SessionSummary -> Close

**Client Deep-Dive Flow:** Select client -> ClientDetailPanel expands inline (250ms ease-out, NO page navigation) -> Metrics row (4 KPIs) -> Sophia diagnosis -> Content queue -> Approve/Edit/Reject per item -> Analytics queries (natural language) -> Back to queue

**Content Regeneration Flow:** Reject -> Guidance (quick tags / typed / voice) -> Regenerate -> New draft with "Guidance applied" label -> Approve/Edit/Reject again -> After 3+ rejections: auto-suggest calibration or manual draft or skip

**Key UX principles from PRD user-journeys.md (Journey 3: Tayo Daily Operations):**
- Context switching is conversational: "Let's talk about Shane's bakery" loads full context
- Cross-client insights surface proactively with drafted content already adapted per voice profile
- Operator time target: 6.75 min/client at maturity, under 45 min total for 20 clients
- "Good morning Tayo! 4 posts ready" personality is part of the interface, not decorative

### Conversation Flow Patterns (from ux-consistency-patterns.md)

**Message types in the chat stream:**

| Type | Visual | Position |
|------|--------|----------|
| Operator message | Sage-dim background, right-aligned, rounded card, max-width 400px | Right side |
| Sophia commentary | Surface card, sage left border, radial glow, serif italic header | Left side, full width |
| Sophia visual response | InlineChart, ClientDetailPanel, BatchApprovalGrid | Left side, full width |
| System timestamp | Centered, muted text, small size | Center |
| Insight card | Sage-tinted border, icon container, action buttons | Left side, full width |

### Navigation Patterns (from ux-consistency-patterns.md)

- NO sidebar, NO hamburger menu, NO breadcrumbs
- Nav bar (top): Sophia logo/name + section tabs
- Tabs represent conversation topics, not pages. Clicking = asking Sophia to show that view
- Tab switching: 150ms cross-fade
- Max depth: 2 (portfolio grid -> client detail). Never 3+ levels
- Browser back works -- each major view updates URL hash
- `Escape` collapses any expanded panel

### Empty & Edge States (from ux-consistency-patterns.md)

| State | UI | Sophia Response |
|-------|----|-----------------|
| First run (no clients) | Empty grid + centered "No clients yet" | "Ready when you are..." |
| Queue already clear | HealthStrip "0 remaining" + `Check` | "Nothing needs your attention today..." |
| All clients cruising | Skip attention/calibrating sections | "Clean portfolio today. Quick batch review." |
| Network offline | Amber banner + cached data + "Last updated: [time]" | Input shows "Offline -- reconnecting..." |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.133 | Backend API + SSE endpoints + Telegram webhook | Already in project (pyproject.toml). Starlette SSE support via sse-starlette. Single process serves all surfaces |
| sse-starlette | 3.2.x | Server-Sent Events for real-time updates | Production-ready SSE for Starlette/FastAPI. W3C spec compliant. Async-native. Latest release confirmed current (Feb 2026). Auto-reconnects by spec |
| python-telegram-bot | 22.6 | Telegram bot with inline keyboards, ConversationHandler | v22.6 is current stable (Jan 24, 2026 release confirmed on PyPI). Fully async (asyncio). Webhook mode runs in same FastAPI process via lifespan |
| React | 19.x | Frontend UI framework | Current stable. Improved Suspense, use() hook, ref-as-prop |
| Vite | 6.x | Frontend build tool + dev server | Standard React build tool. HMR, proxy to FastAPI backend |
| shadcn/ui | latest | UI component primitives (Radix UI) | UX spec decision (component-strategy.md). Copy-paste components, full theming control for Midnight Sage. Tailwind v4 supported |
| Tailwind CSS | 4.x | Utility-first CSS | UX spec decision. CSS-first configuration in v4. @tailwindcss/vite plugin. Native CSS custom properties |
| TanStack Query | 5.x | Server state management, cache invalidation | SSE events trigger invalidateQueries for real-time UI updates. Targeted invalidation by query key |
| React Router | 7.x | Client-side routing (tab-based navigation) | v7 is current (consolidated package -- import from "react-router" not "react-router-dom"). Data router architecture. Object-based route definitions |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Inter (self-hosted or Google Fonts) | variable | Data/interface typography | All operator UI text, numbers, labels. UX spec: 14px body, 600 semibold headings, tabular nums |
| Instrument Serif (self-hosted) | italic only | Sophia personality typography | Sophia headers, insight labels, session titles. MUST self-host with `font-display: swap` + `<link rel="preload">` per visual-design-foundation.md |
| Lucide React | latest | Icon set (Lucide exclusively, NO emoji) | All icons per component-strategy.md icon mapping. Tree-shaking. Check, Pencil, X, Mic, ArrowUp, Circle, etc. |
| shadcn-chat (jakobhoeg) | latest | Chat UI components (ChatBubble, ChatInput) | Chat-first conversation thread. Copy via CLI (npx shadcn-chat-cli add). Customize for Midnight Sage. MIT license |
| motion (formerly Framer Motion) | 12.x | Micro-interactions and transitions | **CRITICAL: Package renamed from "framer-motion" to "motion". Import from "motion/react".** Approved fade, batch stagger, regeneration slide, session summary animation. React 19 compatible (v12.34.3+) |
| date-fns | latest | Date/time formatting and manipulation | Scheduling, posting times, freshness windows, relative time display |
| APScheduler | 3.x | Background job scheduler | Publishing queue execution at scheduled times. Runs within FastAPI process. SQLAlchemy job store for persistence |
| @dnd-kit/react | 0.3.x | Drag and drop | Content calendar reordering. Accessible, keyboard support built in. Latest version 0.3.2 (Feb 2026). **Note: new package is @dnd-kit/react not @dnd-kit/core** |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SSE (sse-starlette) | WebSocket | WebSocket is full-duplex but adds connection management complexity. SSE is simpler for unidirectional server-to-client push. Architecture doc says WebSocket -- SSE is simpler for Phase 4 scope; can upgrade later. The frontend useSSE hook can be swapped without changing the TanStack Query invalidation pattern |
| APScheduler 3.x | APScheduler 4.x | v4 has a redesigned data store system (Task/Schedule/Job split) but is still pre-release. Stick with proven 3.x for now |
| APScheduler | Celery | Celery requires a broker (Redis/RabbitMQ). APScheduler runs in-process. Single-operator scale doesn't need distributed task queue |
| shadcn-chat | Custom chat components | shadcn-chat provides proven ChatBubble/ChatInput components. Customize over build from scratch |
| motion | CSS animations | motion (formerly Framer Motion) gives declarative animation control for complex micro-interactions (stagger, layout animation). CSS sufficient for simple transitions but not for the locked stagger/slide patterns in ux-consistency-patterns.md |
| React Router 7 | TanStack Router | React Router 7 is more mature, larger community, simpler for tab-based navigation. TanStack Router better for complex type-safe routing but overkill here |

**Installation (backend):**
```bash
cd backend
uv add sse-starlette python-telegram-bot apscheduler
```

**Installation (frontend):**
```bash
cd frontend
pnpm create vite@latest . --template react-swc-ts
pnpm install
pnpm add react-router @tanstack/react-query date-fns motion lucide-react @dnd-kit/react
pnpm add -D @types/node tailwindcss @tailwindcss/vite
npx shadcn@latest init
npx shadcn-chat-cli add
```

**Note:** React Router 7 uses `react-router` package (NOT `react-router-dom`). motion uses `motion` package (NOT `framer-motion`).

## Architecture Patterns

### Recommended Project Structure

```
backend/src/sophia/
├── approval/              # NEW: Approval workflow
│   ├── __init__.py
│   ├── models.py          # PublishingQueueEntry, RecoveryLog, ApprovalEvent, NotificationPreference
│   ├── schemas.py         # Pydantic schemas for approval actions
│   ├── service.py         # approve_draft, reject_draft, edit_draft, skip_draft (state machine)
│   ├── router.py          # FastAPI REST endpoints for approval actions
│   └── events.py          # SSE event bus (in-memory broadcast)
├── publishing/            # NEW: Publishing pipeline
│   ├── __init__.py
│   ├── models.py          # PublishResult model
│   ├── scheduler.py       # APScheduler-based publishing queue
│   ├── executor.py        # MCP dispatch to Facebook/Instagram
│   ├── rate_limiter.py    # Per-platform rate limit tracking
│   └── recovery.py        # Content recovery protocol
├── telegram/              # NEW: Telegram bot
│   ├── __init__.py
│   ├── bot.py             # Application builder, handlers, webhook setup
│   ├── handlers.py        # Approval, recovery, notification handlers
│   └── formatters.py      # Message formatting for content cards
├── content/               # EXISTING: Extended with approval status transitions
├── db/                    # EXISTING
├── ...

frontend/src/
├── components/
│   ├── ui/                # shadcn/ui primitives (Button, Badge, Card, etc.)
│   ├── chat/              # Chat thread, SophiaCommentary, operator messages
│   ├── approval/          # ContentItem, BatchApprovalGrid, BatchApprovalItem, QuickTagSelector
│   ├── health/            # HealthStrip, status indicators
│   ├── portfolio/         # ClientTile, PortfolioGrid, InsightCard
│   ├── client/            # ClientDetailPanel
│   ├── calendar/          # Content calendar, drag-to-reorder
│   ├── session/           # SessionSummary
│   └── voice/             # Web Speech API integration
├── hooks/
│   ├── useSSE.ts          # SSE connection + TanStack Query invalidation
│   ├── useApproval.ts     # Approval action mutations
│   ├── useVoiceInput.ts   # Web Speech API hook
│   └── useKeyboardShortcuts.ts
├── lib/
│   ├── api.ts             # API client (fetch wrapper)
│   ├── sse.ts             # EventSource management
│   └── theme.ts           # Midnight Sage design tokens
├── routes/                # React Router 7 route definitions
│   ├── morning-brief.tsx  # PortfolioGrid + HealthStrip + SophiaCommentary
│   ├── approval-queue.tsx # BatchApprovalGrid
│   ├── client.tsx         # ClientDetailPanel (parameterized by client ID)
│   ├── calendar.tsx       # Content calendar
│   ├── analytics.tsx      # Analytics tab (minimal for Phase 4)
│   └── layout.tsx         # App shell: nav tabs + health strip + chat input
├── styles/
│   └── tokens.css         # CSS custom properties for Midnight Sage
└── App.tsx                # Router, SSE provider, layout shell
```

### Pattern 1: SSE Event Bus for Real-Time Sync

**What:** In-memory event bus that broadcasts state changes to all connected SSE clients. Approval actions, publishing events, and recovery operations all publish events. Web app subscribes via EventSource. TanStack Query cache invalidated on event receipt.

**When to use:** Any state change that should reflect across interfaces instantly (APPR-05).

**Example:**
```python
# backend/src/sophia/approval/events.py
import asyncio
import json
from typing import AsyncGenerator

class ApprovalEventBus:
    """In-memory pub/sub for approval state changes."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._max_subscribers = 10  # Defensive: single operator, few tabs

    async def publish(self, event_type: str, data: dict):
        """Broadcast event to all subscribers."""
        event = {"type": event_type, "data": data}
        for queue in self._subscribers:
            await queue.put(event)

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        """Yield events as they arrive. Cleans up on disconnect."""
        if len(self._subscribers) >= self._max_subscribers:
            raise RuntimeError("Too many SSE subscribers")
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers.remove(queue)

# Singleton for the process
event_bus = ApprovalEventBus()
```

```python
# SSE endpoint in FastAPI
from sse_starlette.sse import EventSourceResponse

@router.get("/api/events")
async def event_stream():
    """SSE endpoint for real-time approval state updates."""
    async def generate():
        async for event in event_bus.subscribe():
            yield {
                "event": event["type"],
                "data": json.dumps(event["data"]),
                "retry": 5000,  # Client reconnect delay in ms
            }
    return EventSourceResponse(generate())
```

```typescript
// frontend/src/hooks/useSSE.ts
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

export function useSSE() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const source = new EventSource('/api/events');

    source.addEventListener('approval_changed', (e) => {
      const data = JSON.parse(e.data);
      queryClient.invalidateQueries({ queryKey: ['drafts', data.client_id] });
      queryClient.invalidateQueries({ queryKey: ['health-strip'] });
    });

    source.addEventListener('publish_complete', (e) => {
      const data = JSON.parse(e.data);
      queryClient.invalidateQueries({ queryKey: ['calendar', data.client_id] });
    });

    source.addEventListener('recovery_complete', (e) => {
      const data = JSON.parse(e.data);
      queryClient.invalidateQueries({ queryKey: ['drafts', data.client_id] });
      queryClient.invalidateQueries({ queryKey: ['calendar', data.client_id] });
    });

    source.onerror = () => {
      // EventSource auto-reconnects by W3C spec
    };

    return () => source.close();
  }, [queryClient]);
}
```

### Pattern 2: Approval State Machine

**What:** ContentDraft.status transitions are enforced by a state machine in the approval service. No direct status writes -- all transitions go through the service which validates the transition, updates the DB, publishes events, and logs to audit.

**When to use:** Every approval action (approve, reject, edit, skip, publish, recover).

**Example:**
```python
# Valid state transitions
VALID_TRANSITIONS = {
    "draft": {"in_review"},
    "in_review": {"approved", "rejected", "skipped"},
    "approved": {"published", "in_review"},  # in_review for re-edit
    "rejected": {"in_review"},               # re-submit after regeneration
    "skipped": {"in_review"},                # operator reconsiders
    "published": {"recovered"},              # content recovery
    "recovered": {"in_review"},              # replacement draft
}

async def transition_draft(
    db: Session, draft_id: int, new_status: str,
    actor: str = "operator", **kwargs
) -> ContentDraft:
    draft = db.query(ContentDraft).get(draft_id)
    if draft is None:
        raise ContentNotFoundError(f"Draft {draft_id} not found")

    if new_status not in VALID_TRANSITIONS.get(draft.status, set()):
        raise InvalidTransitionError(
            f"Cannot transition from '{draft.status}' to '{new_status}'"
        )

    old_status = draft.status
    draft.status = new_status
    # Apply kwargs (edited copy, custom time, etc.)
    if "custom_post_time" in kwargs:
        draft.custom_post_time = kwargs["custom_post_time"]
    if "edited_copy" in kwargs:
        draft.copy = kwargs["edited_copy"]

    # Audit log
    db.add(AuditLog(
        client_id=draft.client_id,
        action=f"draft_{new_status}",
        actor=actor,
        details={"draft_id": draft_id, "from": old_status, "to": new_status, **kwargs},
    ))
    db.commit()

    # Broadcast to all interfaces
    await event_bus.publish("approval_changed", {
        "draft_id": draft_id, "client_id": draft.client_id,
        "old_status": old_status, "new_status": new_status,
    })
    return draft
```

### Pattern 3: Telegram Bot in FastAPI Lifespan

**What:** python-telegram-bot Application runs within FastAPI's lifespan context. Webhook endpoint receives updates, bot handlers process them. Same DB session factory, same event bus.

**When to use:** Telegram bot needs to share state with web app and publishing pipeline.

**Example:**
```python
# backend/src/sophia/telegram/bot.py
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from contextlib import asynccontextmanager
from fastapi import FastAPI

async def build_telegram_app(token: str, webhook_url: str) -> Application:
    app = (
        Application.builder()
        .token(token)
        .updater(None)  # No polling -- webhook mode
        .build()
    )
    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^approve_"))
    app.add_handler(CallbackQueryHandler(reject_callback, pattern=r"^reject_"))
    app.add_handler(CallbackQueryHandler(edit_callback, pattern=r"^edit_"))
    app.add_handler(CallbackQueryHandler(skip_callback, pattern=r"^skip_"))
    # Recovery handlers
    app.add_handler(CallbackQueryHandler(recovery_callback, pattern=r"^recover_"))
    # Global pause
    app.add_handler(CommandHandler("pause", global_pause_handler))
    app.add_handler(CommandHandler("resume", global_resume_handler))

    await app.bot.set_webhook(url=webhook_url)
    return app

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # Startup: initialize telegram bot
    tg_app = await build_telegram_app(
        token=settings.telegram_bot_token,
        webhook_url=f"{settings.base_url}/api/telegram/webhook",
    )
    await tg_app.initialize()
    await tg_app.start()
    fastapi_app.state.telegram = tg_app
    yield
    # Shutdown
    await tg_app.stop()
    await tg_app.shutdown()
```

### Pattern 4: Publishing Queue with APScheduler

**What:** Approved content enters a publishing queue. APScheduler runs as a background task within the FastAPI process. At the scheduled time, the executor dispatches to the appropriate MCP server (Facebook or Instagram). Rate limits are checked before execution. Failures retry with exponential backoff up to 3 times.

**When to use:** After approval, content needs to publish at the right time respecting cadence and rate limits.

**Example:**
```python
# backend/src/sophia/publishing/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# Use separate unencrypted SQLite for job store (publishing schedule not sensitive)
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///data/scheduler.db')
}
scheduler = AsyncIOScheduler(jobstores=jobstores)

async def schedule_publish(draft_id: int, publish_at: datetime, platform: str):
    scheduler.add_job(
        execute_publish,
        trigger='date',
        run_date=publish_at,
        args=[draft_id, platform],
        id=f"publish_{draft_id}_{platform}",
        replace_existing=True,
    )

async def execute_publish(draft_id: int, platform: str):
    # Check rate limits
    if not rate_limiter.can_publish(platform):
        new_time = rate_limiter.next_available(platform)
        await schedule_publish(draft_id, new_time, platform)
        return

    try:
        result = await mcp_dispatch(draft_id, platform)
        await transition_draft(db, draft_id, "published", actor="sophia:publisher")
        # Store platform post ID and URL for recovery
        # Send Telegram confirmation with live link
        await event_bus.publish("publish_complete", {
            "draft_id": draft_id, "client_id": result.client_id,
            "platform": platform, "url": result.platform_post_url,
        })
    except PublishError as e:
        # Retry up to 3x with exponential backoff
        entry = get_queue_entry(draft_id, platform)
        if entry.retry_count < 3:
            entry.retry_count += 1
            delay = 2 ** entry.retry_count * 60  # 2, 4, 8 minutes
            await schedule_publish(draft_id, now() + timedelta(seconds=delay), platform)
        else:
            entry.status = "failed"
            entry.error_message = str(e)
            # Alert operator via Telegram
            await send_telegram_alert(entry.client_id, f"Publishing failed for {platform}: {e}")
```

### Anti-Patterns to Avoid

- **Polling for state sync:** Do not poll the database for approval state changes. Use SSE event bus for push-based updates. Polling at 20-client scale creates unnecessary DB load and latency
- **Direct status writes:** Never do `draft.status = "approved"` outside the approval service. All transitions must go through the state machine to ensure event broadcasting, audit logging, and transition validation
- **Coupling Telegram to web app logic:** Telegram handlers should call the same approval service as the web app. Never duplicate business logic in Telegram handlers
- **Blocking MCP calls in request handlers:** MCP dispatch (publishing) should never block a FastAPI request handler. Use the scheduler or background tasks
- **Frontend polling for freshness:** Use SSE for real-time updates. TanStack Query's staleTime and refetchOnWindowFocus handle background freshness without manual polling
- **Hardcoding rate limits:** Rate limits change. Store them in config (or dynamically detect from API headers). Facebook's `x-business-use-case-usage` header provides real-time usage data
- **Using emoji in the UI:** UX spec mandates Lucide icons exclusively throughout. NO emoji anywhere in the interface (component-strategy.md)
- **Using spinners or "typing..." text:** Sophia thinking indicator is sage dot pulse ONLY (ux-consistency-patterns.md)
- **Sophia commentary on every approve:** Commentary only after significant actions (batch approve, calibration complete, insight decisions). Individual approves get visual feedback (fade/check) but NO Sophia commentary (ux-consistency-patterns.md)
- **Page navigation for drill-downs:** ClientDetailPanel expands inline (250ms ease-out). No route change. Panel expansion over page routing (user-journey-flows.md)
- **Using "framer-motion" package name:** Library renamed to "motion". Import from "motion/react" not "framer-motion"
- **Using "react-router-dom":** React Router 7 consolidated to "react-router" package

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE implementation | Custom HTTP streaming | sse-starlette 3.2.x | W3C spec compliance, connection management, keep-alive, async generator support |
| Telegram bot framework | Raw HTTP to Telegram API | python-telegram-bot v22.6 | Conversation state, inline keyboards, webhook management, update parsing, error handling |
| Job scheduling | Custom timer/cron loop | APScheduler 3.x | Missed job recovery, persistent job store (SQLite), timezone handling, job lifecycle |
| Chat UI components | Custom React chat from scratch | shadcn-chat + shadcn/ui | Proven ChatBubble/ChatInput. Copy-paste, customize theming. MIT license |
| Facebook/Instagram API | Direct Graph API HTTP calls | MCP servers (facebook-mcp-server, ig-mcp) | MCP abstraction isolates platform API changes. Tool-based interface matches agent architecture |
| Date/time handling | Manual date arithmetic | date-fns | Timezone handling, relative time, formatting. Scheduling requires correct TZ math |
| Animation orchestration | Complex CSS keyframe chains | motion (React) | Declarative stagger, layout animation, gesture. Required for locked micro-interaction patterns |
| Drag-and-drop | Custom mouse event handling | @dnd-kit/react | Accessible drag-and-drop for content calendar reordering. Keyboard support built in |
| Voice recognition | Custom audio processing | Web Speech API (SpeechRecognition) | Browser-native, no library needed. Chrome/Edge support sufficient for single operator |
| Icon set | Mixed icon sources | Lucide React (exclusively) | UX spec mandates Lucide only. Tree-shaking. Consistent visual language |
| Design tokens | Hardcoded CSS values | CSS custom properties + Tailwind v4 | Single-file theme changes. UX spec defines exact token values. Tailwind v4 native CSS properties |

**Key insight:** Phase 4 touches many surface areas but each has a mature solution. The complexity is in integration, state management, and faithfully implementing the UX specification -- not in building individual components from scratch.

## Common Pitfalls

### Pitfall 1: Race Conditions in Approval State
**What goes wrong:** Operator approves on Telegram while web app shows the same draft. Both try to transition from "in_review" to "approved". Database gets conflicting writes.
**Why it happens:** Multiple interfaces writing to the same draft without coordination.
**How to avoid:** Optimistic locking on ContentDraft (check current status before transition). The approval state machine validates transitions. If a race occurs, the second caller gets a 409 Conflict and the SSE event updates their UI.
**Warning signs:** Duplicate audit log entries for the same transition.

### Pitfall 2: SSE Connection Leaks
**What goes wrong:** Browser tabs left open accumulate SSE connections. Each subscriber adds a queue to the event bus. Memory grows, broadcast slows.
**Why it happens:** EventSource reconnects automatically on disconnection but old subscriptions aren't cleaned up.
**How to avoid:** The subscribe() generator's finally block must remove the queue. Set a maximum subscriber count (e.g., 10). Log warning when approaching limit. Single operator won't have many tabs, but defensive coding prevents issues.
**Warning signs:** Growing memory in FastAPI process. Slow event delivery.

### Pitfall 3: Instagram Container Publishing Two-Step
**What goes wrong:** Developer calls a single publish endpoint expecting the post to appear. Nothing happens.
**Why it happens:** Instagram Graph API requires a two-step process: (1) create a media container, (2) publish the container. Container creation is asynchronous for video.
**How to avoid:** The MCP server (ig-mcp) abstracts this via publish_media tool. But if implementing directly, always follow the container pattern. Check container status before publishing. For images, creation is synchronous. For video/reels, poll container status.
**Warning signs:** Instagram publish calls return success but post doesn't appear.

### Pitfall 4: Facebook Token Expiration
**What goes wrong:** Publishing fails after 60 days. All scheduled posts fail.
**Why it happens:** Long-lived user tokens expire after 60 days. Page tokens derived correctly from long-lived user tokens while user is page admin do NOT expire -- but this must be set up correctly.
**How to avoid:** Use page access tokens (not user tokens) for publishing. Generate a never-expiring page token: short-lived user token -> long-lived user token -> exchange for page token via /me/accounts endpoint. Verify with Debug endpoint that "expires: never". Add token health check to morning brief / daily cycle.
**Warning signs:** 401 errors from Graph API. Publishing failure rate suddenly spikes.

### Pitfall 5: Web Speech API Browser Compatibility
**What goes wrong:** Voice input works in development (Chrome) but fails for operator on different browser.
**Why it happens:** SpeechRecognition is only supported in Chrome and Chromium-based browsers (Edge). Firefox and Safari have no or limited support.
**How to avoid:** Feature-detect `window.SpeechRecognition || window.webkitSpeechRecognition`. Show/hide voice button based on support. Single operator (Tayo) likely uses Chrome, but document the requirement. Internet connectivity required (audio sent to cloud for transcription).
**Warning signs:** Voice button visible but non-functional. No error in console (feature simply absent).

### Pitfall 6: Timezone Confusion in Scheduling
**What goes wrong:** Post scheduled for 9 AM EST publishes at 9 AM UTC (4 AM EST).
**Why it happens:** Mixing naive and timezone-aware datetimes. SQLite stores times without timezone. Frontend sends local time. Backend treats it as UTC.
**How to avoid:** Store all times as UTC in the database. Frontend converts to/from operator's timezone for display and input. Use date-fns for timezone conversions. Operator's timezone stored in settings. APScheduler uses UTC internally.
**Warning signs:** Posts publishing at wrong times. Content calendar shows different times than what was scheduled.

### Pitfall 7: Telegram Webhook Not Receiving Updates
**What goes wrong:** Telegram bot stops receiving messages after development restart.
**Why it happens:** Telegram caches the webhook URL. If ngrok URL changes (dev), or FastAPI restarts without re-registering the webhook, updates go to the old URL.
**How to avoid:** Re-register webhook on every FastAPI startup (in lifespan). Use secret_token for webhook verification. Log webhook registration success/failure. For development, use ngrok with a fixed subdomain or cloudflare tunnel.
**Warning signs:** Telegram messages sent but no handler triggered. No errors in logs (updates go to old URL silently).

### Pitfall 8: Instagram Post Deletion Not Supported
**What goes wrong:** Recovery protocol tries to delete Instagram post but ig-mcp has no deletion tool.
**Why it happens:** ig-mcp explicitly lists "Delete media" as a future feature not yet implemented. Instagram Graph API deletion support for Business accounts is poorly documented.
**How to avoid:** Recovery protocol for Instagram must handle gracefully: (1) attempt deletion via API if available, (2) if not supported, archive internally, notify operator with manual deletion instructions, and mark as "manual_recovery_needed". (3) Facebook recovery works via delete_post tool.
**Warning signs:** Recovery operations succeed for Facebook but fail silently for Instagram.

### Pitfall 9: APScheduler + SQLCipher Incompatibility
**What goes wrong:** APScheduler's SQLAlchemy job store fails to connect to the encrypted SQLite database.
**Why it happens:** APScheduler's SQLAlchemyJobStore creates its own engine. SQLCipher connection requires PRAGMA key setup on connect events.
**How to avoid:** Use a separate unencrypted SQLite file for the APScheduler job store. Publishing schedule data (job execution times) is not sensitive -- the actual content is in the encrypted main DB. Separate file also avoids WAL contention.
**Warning signs:** APScheduler startup failures. Jobs not persisting across restarts.

### Pitfall 10: Framer Motion / motion Import Confusion
**What goes wrong:** `import { motion } from 'framer-motion'` fails or installs wrong version.
**Why it happens:** Framer Motion was rebranded as "motion" in late 2024. Package renamed from `framer-motion` to `motion`. Imports changed from `framer-motion` to `motion/react`.
**How to avoid:** Install `motion` (NOT `framer-motion`). Import from `motion/react`. v12.x+ supports React 19.
**Warning signs:** Build errors on import. React 19 peer dependency warnings.

## Code Examples

Verified patterns from official sources:

### Telegram Inline Keyboard for Content Approval
```python
# Source: python-telegram-bot docs, inlinekeyboard2.py example
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

async def send_content_for_review(bot, chat_id, draft):
    """Send a content draft to Telegram with approval buttons."""
    keyboard = [
        [
            InlineKeyboardButton("Approve", callback_data=f"approve_{draft.id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit_{draft.id}"),
        ],
        [
            InlineKeyboardButton("Reject", callback_data=f"reject_{draft.id}"),
            InlineKeyboardButton("Skip", callback_data=f"skip_{draft.id}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"*{draft.client_name}* | {draft.platform.title()}\n\n"
        f"{draft.copy}\n\n"
        f"Image: _{draft.image_prompt}_\n"
        f"Voice: {draft.voice_confidence_pct:.0f}% match"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button press for approval."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    action, draft_id = query.data.split("_", 1)
    draft_id = int(draft_id)

    if action == "approve":
        # Call the same approval service as web app
        async with get_db() as db:
            draft = await transition_draft(db, draft_id, "approved", actor="operator:telegram")
        await query.edit_message_text(
            text=f"Approved! Scheduled for {draft.suggested_post_time}"
        )
```

### Web Speech API Push-to-Talk
```typescript
// Source: MDN Web Speech API docs
// frontend/src/hooks/useVoiceInput.ts
import { useState, useCallback, useRef } from 'react';

interface VoiceResult {
  transcript: string;
  confidence: number;
}

export function useVoiceInput(onResult: (result: VoiceResult) => void) {
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const isSupported = typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);

  const startListening = useCallback(() => {
    if (!isSupported) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;     // Single utterance per push
    recognition.interimResults = false;  // Final results only
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      const result = event.results[0][0];
      onResult({
        transcript: result.transcript,
        confidence: result.confidence,
      });
    };

    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }, [isSupported, onResult]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  return { isListening, isSupported, startListening, stopListening };
}
```

### Midnight Sage Design Tokens
```css
/* frontend/src/styles/tokens.css */
/* Source: visual-design-foundation.md + design-direction-decision.md */

@theme {
  /* Canvas (app background layers) */
  --color-midnight-950: #020509;
  --color-midnight-900: #04070d;
  --color-midnight-800: #0a1019;
  --color-midnight-700: #111a26;

  /* Sage (cruising / healthy / primary accent) */
  --color-sage-500: #4a7c59;
  --color-sage-400: #5a9c6a;
  --color-sage-300: #7ab88a;
  --color-sage-200: #a0d4aa;

  /* Amber (calibrating / in-progress) */
  --color-amber-500: #c58c3c;
  --color-amber-400: #d4a04e;

  /* Coral (attention / problem) */
  --color-coral-500: #c55a5a;
  --color-coral-400: #d47070;

  /* Text */
  --color-text-primary: #e8f0ea;
  --color-text-secondary: #a0b4a8;
  --color-text-muted: #6b8070;

  /* Typography */
  --font-data: 'Inter', sans-serif;
  --font-sophia: 'Instrument Serif', serif;

  /* Spacing base: 4px */
  --spacing-base: 4px;

  /* Effects */
  --glow-sage: radial-gradient(ellipse at center, rgba(74, 124, 89, 0.15), transparent 70%);
  --blur-nav: blur(12px);
  --radius-card: 14px;
}
```

**Note:** Tailwind CSS v4 uses `@theme` directive for custom properties instead of `tailwind.config.js`. All tokens are referenced as CSS custom properties.

### Content Card with Three-Tier Action Hierarchy
```tsx
// frontend/src/components/approval/ContentItem.tsx
// Implements ContentItem sub-component per component-strategy.md
import { Check, Pencil, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Button } from '@/components/ui/button';

interface ContentItemProps {
  draft: ContentDraft;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onEdit: (id: number) => void;
  onSkip: (id: number) => void;
  isApproved?: boolean;
}

function ContentItem({ draft, onApprove, onReject, onEdit, onSkip, isApproved }: ContentItemProps) {
  return (
    <motion.div
      className="rounded-[14px] border border-midnight-700 bg-midnight-800 p-3"
      animate={{ opacity: isApproved ? 0.4 : 1 }}
      transition={{ duration: 0.1 }}  /* <100ms per ux-consistency-patterns.md */
    >
      {/* Header: client + platform */}
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-text-primary">{draft.clientName}</span>
        <span className="text-xs font-medium uppercase text-text-muted tracking-wider">
          {draft.platform}
        </span>
      </div>

      {/* Quality gate badges */}
      <div className="flex gap-2 mb-3">
        <GateBadge gate="voice" passed={draft.gateReport?.voice_alignment?.passed} />
        <GateBadge gate="research" passed={draft.gateReport?.research_grounding?.passed} />
        <GateBadge gate="sensitivity" passed={draft.gateReport?.sensitivity?.passed} />
        <GateBadge gate="originality" passed={draft.gateReport?.plagiarism?.passed} />
      </div>

      {/* Post copy */}
      <p className="text-text-primary text-sm leading-[1.45] mb-3">{draft.copy}</p>

      {/* Metadata row */}
      <div className="flex gap-4 text-xs text-text-secondary mb-3">
        <span>Voice: {draft.voiceConfidencePct?.toFixed(0)}%</span>
        <span>{draft.contentPillar}</span>
        <span>{formatTime(draft.suggestedPostTime)}</span>
      </div>

      {/* Three-tier action buttons: Reject (left) | Edit | Approve (right) */}
      <div className="flex gap-2 justify-end mt-4">
        <Button variant="ghost" size="sm" onClick={() => onReject(draft.id)}>
          <X className="h-4 w-4 mr-1" /> Reject
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onEdit(draft.id)}>
          <Pencil className="h-4 w-4 mr-1" /> Edit
        </Button>
        <Button variant="sage" size="sm" onClick={() => onApprove(draft.id)}>
          <Check className="h-4 w-4 mr-1" /> Approve
        </Button>
      </div>
    </motion.div>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Instagram Basic Display API | Instagram Graph API (unified) | Dec 2024 full deprecation | Basic Display API fully ended. All functionality via Graph API with Business/Creator accounts |
| python-telegram-bot v13 (sync) | python-telegram-bot v22.6 (async) | v20.0 (2023) | Fully asyncio-native. Webhook mode preferred over polling. Latest: Jan 24, 2026 |
| React 18 + CRA | React 19 + Vite 6 | 2024-2025 | CRA deprecated. Vite is standard. React 19: improved Suspense, use() hook, ref-as-prop |
| WebSocket-first for all real-time | SSE for unidirectional, WebSocket for bidirectional | 2024-2025 trend | SSE simpler, auto-reconnects, works through proxies. WebSocket reserved for true bidirectional needs |
| Facebook publish_actions permission | pages_manage_posts permission | 2018+ | publish_actions deprecated. Use pages_manage_posts for page posting |
| shadcn/ui with Tailwind v3 | shadcn/ui with Tailwind v4 | Late 2024 | Tailwind v4 uses CSS-first config via @theme directive. @tailwindcss/vite plugin. Native CSS properties |
| Long polling Telegram bots | Webhook-mode Telegram bots | Best practice since 2020 | Webhooks are more efficient for production. No polling loop. Faster response |
| framer-motion package | motion package | Nov 2024 | Rebranded from Framer Motion to Motion for React. Install `motion` not `framer-motion`. Import from `motion/react` |
| react-router-dom v6 | react-router v7 | Late 2024 | Package consolidated. Import from `react-router` not `react-router-dom`. Object-based route definitions |
| APScheduler 3.x | APScheduler 4.x (pre-release) | In progress | v4 redesigns data stores (Task/Schedule/Job split). Still pre-release. Stick with 3.x |
| @dnd-kit/core | @dnd-kit/react | 2025 | New React-specific package (0.3.x). Better DX for React apps |

**Deprecated/outdated (avoid in implementation):**
- `publish_actions` Facebook permission: Removed 2018. Use `pages_manage_posts`
- Instagram Basic Display API: Fully ended Dec 2024. Use Instagram Graph API
- Create React App (CRA): Deprecated. Use Vite
- python-telegram-bot synchronous API (v13-): v20+ is async-only
- `framer-motion` package name: Use `motion` instead
- `react-router-dom` package: Use `react-router` (v7 consolidated)

## New Database Models

The following new models extend the existing schema for Phase 4:

### PublishingQueueEntry
```python
class PublishingQueueEntry(TimestampMixin, Base):
    """Queue entry for approved content awaiting publication."""
    __tablename__ = "publishing_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publish_mode: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "auto" or "manual"
    status: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False
    )  # "queued", "publishing", "published", "failed", "paused"
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # External platform ID for recovery
    platform_post_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Live URL for confirmation
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # Uploaded image path/URL
```

### RecoveryLog
```python
class RecoveryLog(TimestampMixin, Base):
    """Log of content recovery operations."""
    __tablename__ = "recovery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=False, index=True
    )
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(100), nullable=False)
    urgency: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "immediate" or "review"
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # "pending", "executing", "completed", "failed", "manual_recovery_needed"
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "operator:web", "operator:telegram", "operator:cli", "sophia:monitoring"
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replacement_draft_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_drafts.id"), nullable=True
    )
```

### NotificationPreference
```python
class NotificationPreference(TimestampMixin, Base):
    """Operator notification preferences per channel."""
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )  # "browser", "telegram", "email"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    events: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )  # {"new_content": true, "publish_complete": true, "recovery_needed": true, ...}
```

### GlobalPublishState
```python
class GlobalPublishState(TimestampMixin, Base):
    """Global publishing pause state."""
    __tablename__ = "global_publish_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resume_requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
```

### ContentDraft Status Extension

The existing ContentDraft model's `status` field already supports "draft", "in_review", "approved", "rejected", "published". Phase 4 adds:
- **"skipped"**: Operator deliberately skipped this draft
- **"recovered"**: Published post was taken down via recovery protocol

New fields to add to ContentDraft:
- `approved_at`: DateTime -- when the operator approved
- `approved_by`: String -- which interface ("web", "telegram", "cli")
- `published_at`: DateTime -- when actually published to platform
- `custom_post_time`: DateTime -- operator override of suggested_post_time
- `operator_edits`: JSON -- list of edits made by operator (for learning)

### Settings Extension

New fields for Settings (config.py):
- `telegram_bot_token`: SecretStr -- Telegram bot API token
- `telegram_chat_id`: str -- Operator's Telegram chat ID
- `base_url`: str -- Base URL for webhook registration (ngrok in dev)
- `operator_timezone`: str -- e.g., "America/Toronto" for scheduling
- `facebook_access_token`: SecretStr -- Page access token (never-expiring)
- `facebook_page_id`: str -- Facebook page ID
- `instagram_access_token`: SecretStr -- Instagram long-lived token
- `instagram_business_account_id`: str -- Instagram business account ID
- `facebook_app_id`: str -- Required by ig-mcp
- `facebook_app_secret`: SecretStr -- Required by ig-mcp

## Open Questions

1. **MCP Server Maturity and Coverage**
   - What we know: facebook-mcp-server (HagaiHen) has 28 tools including post_to_facebook, post_image_to_facebook, schedule_post, delete_post. ig-mcp (jlbadano) has 8 tools including publish_media. Both require environment variables for authentication.
   - What's unclear: Production maturity, error handling quality, Instagram carousel/story support in ig-mcp, how well they handle rate limit responses. ig-mcp explicitly does NOT support post deletion (listed as "future feature").
   - Recommendation: Evaluate both MCP servers during implementation. If insufficient, build a thin MCP wrapper around direct Graph API calls. The MCP abstraction is the architecture decision -- the specific server can be swapped. For Instagram deletion, implement graceful degradation with manual recovery instructions.

2. **Instagram Post Deletion via API**
   - What we know: Facebook posts can be deleted via DELETE /{post-id} (delete_post tool). ig-mcp does NOT support deletion. Instagram Graph API deletion documentation is unclear for Business accounts.
   - What's unclear: Whether Instagram Graph API supports DELETE on media objects for Business accounts at all.
   - Recommendation: Research during implementation. Recovery protocol for Instagram should have a "manual_recovery_needed" status path. Operator gets instructions to manually delete from Instagram app. This is acceptable because recovery is a rare operation.

3. **SSE vs WebSocket (Architecture Doc Consideration)**
   - What we know: SSE is simpler and sufficient for Phase 4's unidirectional push pattern. EventSource auto-reconnects by W3C spec.
   - What's unclear: Whether future phases (voice streaming in Sprint 2/3) will require WebSocket.
   - Recommendation: Start with SSE for Phase 4. The frontend useSSE hook can be swapped for useWebSocket later without changing the TanStack Query invalidation pattern. Avoid premature complexity. FR65 (voice input) uses Web Speech API which processes locally in the browser -- no server-side audio streaming needed.

4. **APScheduler Persistence Across Restarts**
   - What we know: APScheduler 3.x can use SQLAlchemy as a job store for persistence.
   - What's unclear: How APScheduler interacts with SQLCipher-encrypted SQLite.
   - Recommendation: Use a separate unencrypted SQLite file for the APScheduler job store. Publishing schedule is not sensitive data (actual content is in the encrypted main DB). Separate file also avoids WAL contention between the main app and the scheduler.

5. **Platform Mockup Preview Rendering**
   - What we know: Operator wants to see how posts will look on Facebook/Instagram before approval (CONTEXT.md locked decision).
   - What's unclear: Best approach -- static CSS mockups vs screenshot rendering vs platform embed.
   - Recommendation: Static CSS mockups that approximate platform layout (text truncation, image placement, character counts). No API calls or screenshots. Start simple, refine based on operator feedback. This is a visual approximation -- "what you see is what gets posted" level fidelity.

6. **Instagram API Rate Limits (Conflicting Sources)**
   - What we know: Some sources say 25 posts/24hrs, others say 100 posts/24hrs for Business accounts.
   - What's unclear: The exact current limit and whether it varies by account age/tier.
   - Recommendation: Use the Content Publishing Limit endpoint (`GET /{ig-user-id}/content_publishing_limit`) to check real-time usage before publishing. Start conservative (25/24hrs), adjust based on actual API response headers. For 20 clients doing 1-2 posts/day each, even 25/24hrs is sufficient (20-40 posts/day).

## Sources

### Primary (HIGH confidence)
- [python-telegram-bot v22.6 docs](https://docs.python-telegram-bot.org/) - v22.6 confirmed on PyPI (Jan 24, 2026). Async API, ConversationHandler, inline keyboards, webhook mode
- [sse-starlette PyPI](https://pypi.org/project/sse-starlette/) - v3.2.0 confirmed current. FastAPI integration, EventSourceResponse
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite) - Tailwind v4 support, React 19 compatibility
- [shadcn/ui Tailwind v4 guide](https://ui.shadcn.com/docs/tailwind-v4) - @theme directive, CSS-first configuration
- [MDN Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) - SpeechRecognition interface, browser support (Chrome/Edge)
- [Can I Use: Speech Recognition](https://caniuse.com/speech-recognition) - Browser compatibility data
- [Motion (formerly Framer Motion)](https://motion.dev/docs/react) - v12.34.3, React 19 compatible, import from "motion/react"
- [React Router v7 upgrade guide](https://reactrouter.com/upgrading/v6) - Package consolidation, data router architecture
- [TanStack Query v5 invalidation](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation) - invalidateQueries API, targeted invalidation by key
- [dnd-kit React](https://dndkit.com/) - v0.3.2, accessible drag-and-drop, keyboard support

### Secondary (MEDIUM confidence)
- [facebook-mcp-server GitHub](https://github.com/HagaiHen/facebook-mcp-server) - 28 tools confirmed including post_to_facebook, schedule_post, delete_post. Env: FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID
- [ig-mcp GitHub](https://github.com/jlbadano/ig-mcp) - 8 tools confirmed including publish_media. Deletion NOT supported ("future feature"). Env: INSTAGRAM_ACCESS_TOKEN, FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, INSTAGRAM_BUSINESS_ACCOUNT_ID
- [shadcn-chat GitHub](https://github.com/jakobhoeg/shadcn-chat) - ChatBubble, ChatInput, expandable chat. MIT license. Active maintenance (1400+ stars)
- [Facebook page token setup](https://blogambitious.com/create-permanent-facebook-page-open-graph-api-access-token/) - Never-expiring page token process confirmed working Feb 2025
- [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/userguide.html) - AsyncIOScheduler, SQLAlchemy job store

### Tertiary (LOW confidence)
- Instagram Graph API post deletion capability -- not definitively confirmed via official docs. ig-mcp explicitly does NOT support it. Needs validation during implementation
- Instagram publishing rate limit (25 vs 100 posts/24hrs) -- conflicting sources. Use Content Publishing Limit endpoint for real-time check
- APScheduler + SQLCipher job store compatibility -- theoretically works via SQLAlchemy but not verified. Recommendation: use separate unencrypted SQLite

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified via official docs/PyPI with current versions confirmed. Package renames caught (motion, react-router)
- Architecture patterns: HIGH - SSE, state machine, Telegram webhook integration, APScheduler are well-documented patterns with multiple production examples
- UX specification compliance: HIGH - Full cross-reference against 7 BMAD UX spec documents. Component specs, action hierarchy, feedback timings, design tokens all documented
- Pitfalls: MEDIUM-HIGH - Common issues verified. Instagram deletion and APScheduler+SQLCipher are lower confidence. Framer Motion rename caught as new pitfall
- Frontend stack: MEDIUM-HIGH - shadcn/ui + Vite + Tailwind v4 + React 19 is well-documented. Package renames verified. Chat components (shadcn-chat) are community-maintained
- MCP server maturity: MEDIUM - Both servers exist and advertise publishing capabilities. ig-mcp confirmed no deletion support. Production battle-testing unknown

**Research date:** 2026-02-27
**Valid until:** 2026-03-27 (30 days -- stable domain, libraries mature)
