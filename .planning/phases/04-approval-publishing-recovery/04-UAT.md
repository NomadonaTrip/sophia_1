---
status: complete
phase: 04-approval-publishing-recovery
source: [04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md, 04-05-SUMMARY.md, 04-06-SUMMARY.md]
started: 2026-02-28T08:00:00Z
updated: 2026-02-28T09:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Frontend loads with Midnight Sage design system
expected: Open http://localhost:5173 in browser. Page renders with dark background (#0a0f0a or similar deep green-black), sage/green accent colors, and all content centered at 60% viewport width. No white/default theme visible.
result: pass

### 2. App shell with nav tabs and health strip
expected: Sticky header at top with "Sophia" branding. Six nav tabs evenly distributed across the 60% width. HealthStrip bar visible below header showing colored status dots (sage=cruising, amber=calibrating, coral=attention).
result: pass

### 3. Collapsible route content panel
expected: A "Focus chat" toggle button is visible. Clicking it collapses the route content area (cards/grids) and expands the chat conversation area to fill the screen. Clicking again restores the cards.
result: pass

### 4. Approval queue page with content cards
expected: Navigate to Approval Queue tab. Content cards display (or an empty state if no drafts in queue). Each card shows the draft copy, client name, content pillar, voice alignment, and gate badges. Three action buttons: Reject (left, ghost style), Edit (middle, secondary), Approve (right, sage/green primary).
result: pass

### 5. Keyboard shortcuts in approval queue
expected: While on the Approval Queue page (with no text input focused), press A to approve, R to reject, E to edit, N for next item, Tab to expand details, Escape to close. Shortcuts should NOT fire when typing in a text input or the chat bar.
result: skipped
reason: No drafts in queue to test keyboard shortcuts against

### 6. Portfolio grid on Morning Brief
expected: Navigate to Morning Brief tab. Client tiles display in a grid sorted by urgency (attention clients first, then calibrating, then cruising). Each tile shows client name, a sparkline or trend indicator, and a colored status border.
result: pass

### 7. Client detail panel expands inline
expected: Click on a client tile in the portfolio grid. A detail panel expands inline below the tile (250ms ease-out animation, no page navigation). Panel shows client metrics, content queue, and diagnosis info. Click again or press Escape to collapse.
result: pass

### 8. Platform mockup preview on content card
expected: On a content card in the approval queue, a platform mockup preview section shows how the post would appear on Facebook or Instagram (with profile picture area, post text, image placeholder, and engagement icons styled per platform).
result: skipped
reason: No drafts in queue to test platform mockup preview

### 9. Image upload on content draft
expected: On a content card, click the image upload area/button. Select a local image file. The upload succeeds and the image path displays on the card. (Backend persists image_url to the draft record.)
result: skipped
reason: No drafts in queue to test image upload

### 10. Voice input mic button (Chrome only)
expected: In Chrome browser, the ChatInputBar at the bottom shows a microphone icon button. Clicking it activates push-to-talk (mic icon changes state). Speaking a command like "approve" is transcribed and parsed. In non-Chrome browsers, the mic button is hidden.
result: pass

### 11. Chat input bar sends messages
expected: Type a message in the ChatInputBar at the bottom of the page and press Enter or click Send. The message appears in the chat conversation area above as a user bubble (right-aligned). Sophia's responses (if any) appear left-aligned with Instrument Serif italic font.
result: pass

### 12. SSE real-time event stream
expected: Open browser dev tools Network tab, filter by EventStream. A persistent connection to /api/events is established. When an approval action occurs (approve/reject), an SSE event fires and the UI updates without manual refresh.
result: pass

### 13. Backend starts without hanging
expected: Run `cd backend && uvicorn sophia.main:app --reload` from the terminal. The server starts within 10-15 seconds (no 5+ minute hang from heavy imports). Endpoints respond at http://localhost:8000/docs (FastAPI Swagger UI).
result: pass

### 14. Batch approval grid for cruising clients
expected: On the Approval Queue or Morning Brief, if any clients have "cruising" status, their content appears in a compact 2-column batch approval grid with an "Approve All" button in the header for one-click bulk approval.
result: skipped
reason: No drafts in queue to test batch approval grid

## Summary

total: 14
passed: 10
issues: 0
pending: 0
skipped: 4

## Gaps

[none yet]
