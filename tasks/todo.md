# 04-04 Remaining Work

## Committed (0a4b0b9)
- [x] Fix 7 approval queue UI bugs (approval-queue.tsx rewrite, ContentItem triggers, BatchApprovalItem sync)
- [x] Wire approval router _get_db with real SessionLocal
- [x] Enrich /approval/queue endpoint with all ContentItem fields
- [x] Lazy-load spacy/textstat to fix NTFS startup hang
- [x] Seed script for demo data (seed_demo.py)

## Remaining 04-04 Items
- [x] Wire content router _get_db (same lazy pattern as approval router — `backend/src/sophia/content/router.py` line 45)
- [x] Wire research router _get_db_session (same pattern — `backend/src/sophia/research/router.py` line 39)
- [ ] Calibration auto-suggest after 3+ rejections (useApproval.ts already tracks rejectionCounts, need UI trigger)
- [ ] Session summary auto-trigger
- [ ] Frontend-backend integration testing (verify all 7 bugs fixed end-to-end in browser)
- [ ] Commit README for frontend (currently untracked `frontend/README.md`)

## After 04-04
- [ ] Plan 04-05: Telegram Bot + Web Speech API voice input

## Key Files
- `backend/src/sophia/approval/router.py` — wired _get_db, enriched queue endpoint
- `backend/src/sophia/content/voice_alignment.py` — lazy spacy
- `frontend/src/routes/approval-queue.tsx` — dual-mode with real data
- `frontend/src/components/approval/ContentItem.tsx` — trigger props
- `frontend/src/components/approval/BatchApprovalItem.tsx` — prop sync fix

## Dev Notes
- Backend runs with: `uvicorn sophia.main:app --reload` from `backend/`
- spacy import is lazy now — first voice alignment call will be slow, subsequent fast
- DB at `/home/nomad/sophia/data/sophia.db` (ext4, encrypted SQLCipher)
- Seed with: `.venv/bin/python seed_demo.py` from `backend/`
- Frontend build verified: `pnpm build` passes clean
