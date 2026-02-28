---
phase: 04-approval-publishing-recovery
plan: 04
subsystem: ui
tags: [react, tanstack-query, sse, keyboard-shortcuts, motion, vite, tailwind]

# Dependency graph
requires:
  - phase: 04-01
    provides: Backend approval REST API, SSE event bus, state machine
  - phase: 04-02
    provides: Vite + React scaffold, Midnight Sage design system, layout shell
provides:
  - SSE-powered real-time sync hook (useSSE) with TanStack Query cache invalidation
  - Approval mutation hooks (approve/reject/edit/skip/upload-image) with optimistic updates
  - Keyboard shortcuts for rapid queue clearing (A/E/R/N/Tab/Escape)
  - ContentItem component with three-tier action hierarchy and locked micro-interactions
  - Batch approval grid for cruising-client bulk operations
  - Portfolio grid with urgency-sorted client tiles and progressive loading
  - Client detail panel with inline expansion (no page navigation)
  - Platform mockup previews for Facebook and Instagram
  - CopyReadyPackage for manual publish mode
  - Network error handling with auto-retry and amber banner
  - Stale content toast via SSE events
  - Recovery dialog for published post recovery
affects: [04-05, phase-5]

# Tech tracking
tech-stack:
  added: [motion/react, lucide-react (already present)]
  patterns: [SSE EventSource with TanStack Query invalidation, optimistic mutation updates, keyboard shortcut hook with active-element guard, three-tier action hierarchy (reject/edit/approve)]

key-files:
  created:
    - frontend/src/hooks/useSSE.ts
    - frontend/src/hooks/useApproval.ts
    - frontend/src/hooks/useKeyboardShortcuts.ts
    - frontend/src/hooks/useNetworkError.ts
    - frontend/src/components/approval/ContentItem.tsx
    - frontend/src/components/approval/QuickTagSelector.tsx
    - frontend/src/components/approval/PlatformMockupPreview.tsx
    - frontend/src/components/approval/CopyReadyPackage.tsx
    - frontend/src/components/approval/NetworkErrorBanner.tsx
    - frontend/src/components/approval/StaleContentToast.tsx
    - frontend/src/components/approval/BatchApprovalGrid.tsx
    - frontend/src/components/approval/BatchApprovalItem.tsx
    - frontend/src/components/approval/RecoveryDialog.tsx
    - frontend/src/components/portfolio/ClientTile.tsx
    - frontend/src/components/portfolio/PortfolioGrid.tsx
    - frontend/src/components/portfolio/InsightCard.tsx
    - frontend/src/components/client/ClientDetailPanel.tsx
    - frontend/src/routes/morning-brief.tsx
    - frontend/src/routes/approval-queue.tsx
    - frontend/src/routes/client.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/routes/layout.tsx
    - frontend/src/components/chat/ChatInputBar.tsx
    - frontend/src/components/chat/ChatMessageArea.tsx
    - frontend/src/components/health/HealthStrip.tsx
    - frontend/src/styles/globals.css

key-decisions:
  - "Approval mutations wired to real backend endpoints with TanStack Query optimistic updates"
  - "Lazy-loaded spacy in voice_alignment.py to prevent NTFS startup hang"
  - "Session-level rejection tracking in useApproval hook state for calibration auto-suggest"
  - "NetworkErrorBanner with exponential backoff retry (2s/4s/8s) matching CONTEXT.md locked decision"

patterns-established:
  - "SSE EventSource pattern: connect in useSSE hook, invalidate TanStack Query caches per event type"
  - "Three-tier action hierarchy: Reject (left/ghost) | Edit (middle/secondary) | Approve (right/sage-primary)"
  - "Keyboard shortcut hook: keydown listener with document.activeElement guard to avoid capture during text input"
  - "Inline panel expansion: ClientDetailPanel uses 250ms ease-out animation, no route change"
  - "Progressive content loading: attention tiles immediate, calibrating 50ms delay, cruising 100ms stagger"

requirements-completed: [APPR-01, APPR-05]

# Metrics
duration: 25min
completed: 2026-02-28
---

# Phase 4 Plan 04: Frontend Approval UI Summary

**Complete approval interface with SSE real-time sync, three-tier content cards, batch approval, keyboard shortcuts, portfolio grid, and platform mockup previews**

## Performance

- **Duration:** ~25 min (across multiple sessions including checkpoint)
- **Started:** 2026-02-27T22:10:00Z
- **Completed:** 2026-02-28T04:05:38Z
- **Tasks:** 3 (2 auto + 1 checkpoint)
- **Files created/modified:** 28 frontend files

## Accomplishments
- Built the complete operator approval interface with all BMAD-specified micro-interactions: 40% opacity fade on approve (<100ms), coral border pulse on reject, 200ms stagger on batch approve
- SSE-powered real-time sync via EventSource that invalidates TanStack Query caches on approval_changed, publish_complete, recovery_complete, and content_stale events
- Keyboard shortcuts (A/E/R/N/Tab/Escape) enable rapid queue clearing without mouse interaction
- Portfolio grid with urgency-sorted client tiles (attention first), inline-expanding ClientDetailPanel (250ms ease-out, no page navigation), and progressive content loading
- Batch approval grid for cruising clients with "Approve All" one-click operation
- Platform mockup previews showing how posts render on Facebook and Instagram
- CopyReadyPackage for manual publish mode with one-click copy, image prompt, hashtags, suggested time, and platform-specific formatting notes
- Network error handling with amber banner, auto-retry 3x with exponential backoff, and manual retry button

## Task Commits

Each task was committed atomically:

1. **Task 1: SSE hook, approval mutations, keyboard shortcuts, ContentItem with three-tier actions** - `6316ece` (feat)
2. **Task 2: Portfolio grid, client detail panel, batch approval, routes** - `4348227` (feat)
3. **Bug fix: Wire approval queue to real data, fix 7 UI bugs, lazy-load spacy** - `0a4b0b9` (fix)

## Files Created/Modified

**Hooks (4 created):**
- `frontend/src/hooks/useSSE.ts` - SSE EventSource connection with TanStack Query cache invalidation
- `frontend/src/hooks/useApproval.ts` - Approval mutations (approve/reject/edit/skip/upload) with optimistic updates and session rejection tracking
- `frontend/src/hooks/useKeyboardShortcuts.ts` - Keyboard shortcut handler (A/E/R/N/Tab/Escape) with active-element guard
- `frontend/src/hooks/useNetworkError.ts` - Network error state management with retry counter

**Approval Components (8 created):**
- `frontend/src/components/approval/ContentItem.tsx` - Content card with three-tier action hierarchy, provenance display, gate badges, platform mockup, image upload
- `frontend/src/components/approval/QuickTagSelector.tsx` - Rejection feedback tags with multiple selection and typed guidance
- `frontend/src/components/approval/PlatformMockupPreview.tsx` - Facebook/Instagram post preview rendering
- `frontend/src/components/approval/CopyReadyPackage.tsx` - Manual publish copy-ready package with one-click copy
- `frontend/src/components/approval/NetworkErrorBanner.tsx` - Amber network error banner with auto-retry 3x
- `frontend/src/components/approval/StaleContentToast.tsx` - Amber toast for stale draft SSE notifications
- `frontend/src/components/approval/BatchApprovalGrid.tsx` - 2-column batch approval grid with "Approve All" header
- `frontend/src/components/approval/BatchApprovalItem.tsx` - Compact batch approval item with three-tier actions
- `frontend/src/components/approval/RecoveryDialog.tsx` - Recovery dialog with reason input and urgency selector

**Portfolio Components (3 created):**
- `frontend/src/components/portfolio/ClientTile.tsx` - Client overview tile with sparkline, trend arrow, status border
- `frontend/src/components/portfolio/PortfolioGrid.tsx` - Responsive grid (5/3/2 columns) sorted by urgency with progressive loading
- `frontend/src/components/portfolio/InsightCard.tsx` - Cross-client pattern insight card with action buttons

**Client Components (1 created):**
- `frontend/src/components/client/ClientDetailPanel.tsx` - Inline-expanding client detail panel with metrics, diagnosis, content queue

**Routes (3 created):**
- `frontend/src/routes/morning-brief.tsx` - Morning session flow with portfolio grid, insights, session summary
- `frontend/src/routes/approval-queue.tsx` - Focused batch approval view with keyboard shortcuts
- `frontend/src/routes/client.tsx` - Client deep-dive route with ClientDetailPanel

**Modified (6):**
- `frontend/src/App.tsx` - Added route definitions for morning-brief, approval-queue, client
- `frontend/src/routes/layout.tsx` - Activated useSSE hook for real-time sync
- `frontend/src/components/chat/ChatInputBar.tsx` - Bug fixes for input handling
- `frontend/src/components/chat/ChatMessageArea.tsx` - Bug fixes for message display
- `frontend/src/components/health/HealthStrip.tsx` - Bug fixes for health data display
- `frontend/src/styles/globals.css` - Additional utility styles for approval UI

## Decisions Made
- **Approval mutations wired to real backend endpoints**: TanStack Query useMutation with optimistic updates for instant UI feedback, SSE provides authoritative state sync
- **Lazy-loaded spacy in voice_alignment.py**: Prevents 5+ minute startup hang on NTFS mounts in WSL2 (deviation from plan scope, required for backend to run)
- **Session-level rejection tracking**: useState in useApproval hook tracks per-client rejection counts for calibration auto-suggest at 3+ rejections
- **NetworkErrorBanner with exponential backoff**: 2s/4s/8s retry intervals matching the CONTEXT.md locked decision pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wire approval queue to real backend data**
- **Found during:** Checkpoint verification (Task 3)
- **Issue:** Approval queue route used mock data instead of querying real backend API endpoint
- **Fix:** Connected TanStack Query hooks to actual GET /api/approval/queue and GET /api/approval/health-strip endpoints
- **Files modified:** frontend/src/routes/approval-queue.tsx, frontend/src/routes/morning-brief.tsx
- **Committed in:** 0a4b0b9

**2. [Rule 1 - Bug] Fix 7 UI component rendering issues**
- **Found during:** Checkpoint verification (Task 3)
- **Issue:** Various rendering bugs in HealthStrip, ChatInputBar, ChatMessageArea, and route components
- **Fix:** Fixed prop handling, conditional rendering, and state management across 7 components
- **Files modified:** Multiple frontend component files
- **Committed in:** 0a4b0b9

**3. [Rule 3 - Blocking] Lazy-load spacy in voice_alignment.py**
- **Found during:** Checkpoint verification (Task 3)
- **Issue:** Backend startup hung for 5+ minutes due to spacy import at module level on NTFS mount
- **Fix:** Moved spacy import inside function body for lazy loading
- **Files modified:** backend/src/sophia/content/voice_alignment.py
- **Committed in:** 0a4b0b9

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All fixes necessary for correct operation. The lazy-load fix was required to run the backend for verification. No scope creep.

## Issues Encountered
- Backend startup performance on NTFS mounts requires lazy imports for heavy libraries (spacy, textstat) -- this is a known WSL2 issue documented in project memory

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Frontend approval UI complete and operator-verified
- Ready for Plan 04-05 (Telegram bot + browser voice input)
- All BMAD UX consistency patterns implemented: action hierarchy, animation timings, skeleton loading, progressive content loading
- SSE real-time sync operational between backend and frontend (APPR-05 fulfilled)

## Self-Check: PASSED

All 20 key files verified present. All 3 task commits verified in git history (6316ece, 4348227, 0a4b0b9).

---
*Phase: 04-approval-publishing-recovery*
*Completed: 2026-02-28*
