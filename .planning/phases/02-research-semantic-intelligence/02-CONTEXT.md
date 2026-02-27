# Phase 2: Research & Semantic Intelligence - Context

**Gathered:** 2026-02-26
**Updated:** 2026-02-26 (enriched from PRD + UX specs)
**Status:** Ready for planning

<domain>
## Phase Boundary

Sophia can research current conditions scoped to each client's market and build progressive intelligence profiles that compound over time. Covers: market-scoped research engine, competitor monitoring, six-domain intelligence profiles, platform intelligence, algorithm detection, and diagnostic reports. Content generation, approval, and publishing are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Research Sources & Cadence
- Local-first sourcing: Google News/Trends scoped by city, local subreddits, Facebook community groups, municipal/BIA event feeds. Broadens to industry only when local is thin
- Social + web: Monitor public posts, hashtags, and community groups on Facebook/Instagram in addition to web sources
- Daily research cycle: Full targeted scan every morning before content generation, matching the daily ReAct loop
- Targeted depth: 3-5 sources per client per day, focused on what's changed since last cycle
- When local sources are thin, pivot to industry-level sources rather than widening geography
- Per-client configurable source blocklist (excluded sources set during onboarding)
- Shared findings with unique angles: Store finding once, each client gets a tailored content angle to avoid identical content across clients
- Market scope per client: Research scoped to client's defined market (hyperlocal, regional, national, or global) based on the client brief. A landscaper gets KWC local events; a web design agency gets global SaaS trends. The client brief is the north star — Sophia cannot override it

### Research Output & Storage
- Structured findings: Sophia distills raw research into tagged findings (topic, relevance score, content angle, source). Content generator works from these
- Each finding includes 1-2 suggested content angles tailored to the client. Content generator picks the best
- Confidence scoring per finding based on source count and reliability. Content generator can skip low-confidence findings
- Auto-expire with decay: News expires fast (2-3 days), trends slower (1-2 weeks), industry insights persist longer
- Research-to-content attribution: Tag each piece of content with the research findings that inspired it. When content performs well, those research sources get weighted higher

### Research Visibility & Surfacing
- Daily research digest delivered via both Telegram (scannable bullet points) and web dashboard (deeper exploration)
- Immediate flagging of time-sensitive findings (local event tomorrow, viral trend) via push notification. Operator can trigger ad-hoc content cycle
- Flag conflicting information: Surface conflicts between Sophia's understanding and client's website/social media. Operator resolves
- Morning brief integration: Research insights surface as part of Sophia's morning brief commentary — portfolio health, per-client diagnoses, anomalies detected overnight
- Cross-client insight cards: When research reveals patterns spanning multiple clients, surface with evidence-first presentation (data before recommendation). Operator controls which clients the pattern applies to
- Client deep-dive diagnostics: When operator drills into a client, Sophia's pre-written diagnosis explains what research found and recommends action

### Intelligence Profile Structure
- Six domains: business, industry, competitors, customers, product/service offer, sales process
- Dual completeness tracking: Field population percentage (quantitative — percentage of predefined intelligence fields populated per domain) AND depth scoring 1-5 (qualitative — richness of understanding, not just field counts)
- Freshness + depth tracked separately: Both how much Sophia knows and how current it is. Old information flagged for re-research
- Profiles seeded from client onboarding conversation (Phase 1), then Sophia auto-researches to fill gaps (Googles the business, reads their website, checks competitors)
- Gap-filling: Research first, ask operator only when research can't answer (e.g., internal sales process details)
- Timestamped change audit trail: Each intelligence update is timestamped and source-attributed

### Intelligence Profile — Domain Details
- Customers domain: Persona-based ICPs, 2-3 named personas per client with demographics, pain points, content preferences, platform behavior
- Sales process domain: Track customer journey stages (discover, evaluate, buy) AND buying triggers, objections for the ICP, buying decision timeline, conversion points (DMs, website visits), what content actually drives action, and seasonality/purchase cycles
- Product/service offer domain: Actively track current promotions, seasonal services, new product launches. Operator updates when things change. Content aligns with what's being sold NOW. Pricing positioning intelligence is NOT tracked — pricing strategy is the client's domain
- Intelligence drives content strategy: Strong competitive intelligence → differentiation content. Weak customer knowledge → more engagement-focused content to learn

### Intelligence Maturity Milestones (simplified)
- Day 1: Basic profile from onboarding + competitor analysis + industry research. Content can be generated across all six domains
- Month 1: Content performance patterns reveal audience preferences. Engagement rate meets or exceeds pre-Sophia baseline. Platform intelligence has initial entries
- Month 3: Deep competitive positioning with gaps and counter-strategies. Cross-client patterns surfaced in weekly briefings. Platform intelligence cross-referenced across clients
- Month 6: Sophia knows customers better than the client does — buying triggers, objections, decision timelines, seasonality. Intelligence profile is an irreplaceable business asset

### Intelligence Profile — Operator Interface
- Visible + editable: Operator can view domain scores, see what Sophia knows, and correct wrong assumptions
- Flag significant changes: Quiet updates for minor enrichments. Flag operator when something changes materially (new competitor found, business pivot detected, customer segment shift)
- Conversational queries: Operator can ask natural language questions about any domain. "Tell me about Shane's customer demographics" → full persona breakdown
- Auto-generated strategic narrative: 2-3 paragraph plain-English summary per client, updated weekly. Gives operator a quick sense of Sophia's understanding
- Flag conflicts: When Sophia's understanding conflicts with what's on client website/social media, surface to operator for resolution

### Intelligence Profile — Cross-Client
- Anonymized ICP intelligence retained as institutional knowledge: Strip client identity, keep industry + location type + what worked. "A restaurant in small-town Ontario found X effective"
- Platform intelligence: Fully per-client (not per-industry). Each client's platform intelligence built independently from their own data

### Competitor Monitoring
- Competitor discovery: Operator seeds 3-5 known competitors during onboarding. Sophia researches and proposes additional ones for approval
- New competitor proposals: Included in daily digest with context. "Found a potential competitor: [Name]. They post about [X] in [location]. Want me to track them?" One-tap approval
- Active monitoring: 3-5 primary competitors tracked per client. Others on watchlist with monthly deep-scan
- Signals tracked: Content activity + engagement (what competitors post, how often, what gets engagement). Surface content gaps and winning formats
- Trigger thresholds: Engagement decline >20%, posting gaps >7 days, engagement spike >30%, new campaigns in client's niche, emerging competitive positioning
- Organic only for now: No paid ad monitoring. Can expand later
- Opportunity types: Categorize as reactive (competitor made a move, we should respond) or proactive (gap in market we can own). Different urgency and content approach
- Flag competitor inactivity: Alert operator if a competitor goes quiet for an unusual period
- Competitive benchmarks: Track relative performance (post frequency, engagement rates, follower growth vs competitors)
- Basic tone mapping: Categorize each competitor's content tone (professional, casual, humorous, educational) for voice differentiation. No deeper competitor voice analysis
- Direct competitors only: Same-category businesses. No indirect competitor tracking for now
- Opportunities surfaced in daily digest (not separate report)
- Share of voice data collection: Collect raw competitive data (posting frequency, engagement levels, audience mentions relative to client within market scope). Reporting and computed metrics deferred to Phase 5

### Platform Intelligence
- Per-client, per-platform intelligence profiles for each active content platform (Facebook, Instagram, Twitter/X, blog; extensible to future platforms)
- Six tracked dimensions: optimal content length ranges, format effectiveness (carousel vs single image vs video vs text vs thread vs long-form), posting timing patterns, hashtag strategies, content type distribution, engagement pattern differences
- Categorized as "required to play" (table-stakes practices — minimum standards to maintain algorithmic visibility) and "sufficient to win" (differentiating practices that drive above-average results for the client's vertical)
- Data source distinction: Facebook and Instagram intelligence accumulates from automated analytics. Twitter/X and blog intelligence accumulates from operator-reported feedback until API integrations are added
- Platform profiles evolve continuously as Sophia accumulates cross-client performance data per platform
- Platform intelligence depth tracked as a self-improvement metric alongside client intelligence depth — feeds into weekly strategic briefings
- Living platform playbook: Per-platform "what works now" maintained from performance data and industry signals. Content generator uses this to choose formats

### Algorithm Detection & Diagnostics
- Detection method: Cross-client anomaly detection. When multiple clients see similar engagement drops/spikes simultaneously → likely algorithm shift. Single-client changes are content/audience specific
- Complement with industry news: Cross-reference detected anomalies with industry news about platform changes for higher confidence
- Separate reach vs engagement tracking: Track reach signals and engagement signals independently. Posts can get wide reach but low engagement or vice versa
- Response protocol: Alert operator immediately + propose content strategy adjustments + explain what was detected and reasoning. Transparent and proactive
- Gradual adaptation: Shift 20-30% of content approach first. If metrics improve over 1-2 weeks, commit further. Avoids whiplash from temporary platform tests
- Full closed loop: Algorithm detection → strategy adaptation → decision trace logging → platform intelligence profile update (updated "required to play" and "sufficient to win" classifications). Adaptations presented to operator for confirmation during next daily standup or weekly briefing
- Platform-wide intelligence sharing: Algorithm shifts are platform-wide events. Share detection and adaptation strategy across all clients on that platform. Per-client content adjustments still personalized

### Diagnostic Reports
- Trigger criteria: Growth rate drops below 20% weekly improvement target OR falls below the previous period's trajectory. Proactive — don't wait for confirmed decline
- Also: lightweight weekly health check per client to catch slow declines
- Root cause analysis scope: Investigate beyond content into business positioning and marketing mix — content staleness, audience fatigue, competitor gains, algorithm changes, seasonal patterns, positioning mismatches, product-market fit signals
- Structured experiments: Each proposal includes hypothesis, duration (1-2 weeks), success metric, rollback plan. "Try video content for 2 weeks. Success = 20%+ engagement lift"
- Experiments are recommended, not auto-triggered: Operator approves which to run. Maintains human control over strategy
- Full decision trail: Log what changed, why, what data drove the decision, what the old strategy was. Operator can review and reverse
- Prioritized hypotheses with supporting data in every diagnostic report

### Claude's Discretion
- Exact research cycle timing within the daily window
- Source prioritization algorithms and weighting
- Depth scoring rubric details for each intelligence domain
- Semantic search implementation (LanceDB + BGE-M3 architecture)
- Database schema for research findings and intelligence profiles
- Anomaly detection thresholds and statistical methods
- Digest formatting and information hierarchy
- Platform playbook structure and update frequency
- Decision trace storage format

</decisions>

<specifics>
## Specific Ideas

- Research should feel like having a local marketing strategist who reads the newspaper every morning — knows what's happening in town before anyone else
- Intelligence profiles are the competitive moat: switching means abandoning compounding knowledge. Each day Sophia understands the client's market better
- The daily digest should be glanceable on a phone (Telegram) but explorable on desktop (web dashboard)
- Competitor monitoring should surface "this is what they're doing well that you're not" and "here's a gap they're ignoring that you could own"
- Algorithm detection should avoid overreaction — gradual adaptation, not panic pivots
- Cross-client insights should lead with evidence (data) before recommendation — operator trusts the insight because they can see the proof
- Geographic scope issues are research problems — when target audience doesn't match actual audience, Sophia investigates root causes across content, positioning, and broader business factors
- Diagnostics should reach beyond content into business strategy — this is what separates agency-level intelligence from content automation

</specifics>

<deferred>
## Deferred Ideas

- Google Business Profile review monitoring — not in this phase
- Paid ad monitoring (Meta Ad Library) — can expand later
- Indirect competitor tracking — future enhancement
- Per-industry base platform intelligence templates — decided fully per-client instead
- Share of voice computed metrics and reporting — Phase 5
- Decision quality scoring (comparing predicted vs actual outcomes) — Phase 5 evaluation pipeline
- Competitor content format tracking (which formats competitors use) — basic tone mapping is sufficient for now

</deferred>

---

*Phase: 02-research-semantic-intelligence*
*Context gathered: 2026-02-26*
*Context updated: 2026-02-26 (enriched from PRD + UX design specification)*
