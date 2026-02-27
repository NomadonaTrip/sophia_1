---
phase: 01-client-foundation-data-security
plan: 01
subsystem: database
tags: [sqlcipher, sqlalchemy, alembic, pydantic, pydantic-settings, structlog, encrypted-sqlite]

# Dependency graph
requires: []
provides:
  - SQLCipher-encrypted database engine with PRAGMA key injection
  - All Phase 1 ORM models (Client, VoiceProfile, VoiceMaterial, EnrichmentLog, AuditLog, InstitutionalKnowledge)
  - Pydantic v2 schemas for CRUD and response serialization
  - Alembic migration pipeline configured for SQLCipher
  - Application configuration with SecretStr encryption key
  - Encrypted backup utility via ATTACH + sqlcipher_export
  - Exception hierarchy with three-part structure
affects: [01-02, 01-03, 02-01, 02-02, 03-01]

# Tech tracking
tech-stack:
  added: [sqlalchemy-2.0, sqlcipher3-0.6.2, alembic-1.18, pydantic-2.12, pydantic-settings-2.13, structlog-25.5, rapidfuzz-3.14, textstat-0.7]
  patterns: [sqlcipher-pragma-injection, sync-engine-with-wal, json-columns-for-evolving-structures, timestamp-mixin, append-only-audit-log]

key-files:
  created:
    - backend/src/sophia/config.py
    - backend/src/sophia/exceptions.py
    - backend/src/sophia/db/engine.py
    - backend/src/sophia/db/base.py
    - backend/src/sophia/db/backup.py
    - backend/src/sophia/intelligence/models.py
    - backend/src/sophia/intelligence/schemas.py
    - backend/src/sophia/institutional/models.py
    - backend/alembic/env.py
    - backend/alembic/versions/001_initial_schema.py
    - .env.example
  modified: []

key-decisions:
  - "Used get_settings() factory instead of module-level singleton to avoid import-time .env requirement"
  - "Synchronous SQLAlchemy engine -- async provides no benefit with SQLCipher (no async driver exists)"
  - "JSON columns for evolving structures (voice profile, onboarding state, guardrails) -- avoids migrations for dimension changes"
  - "No cross-client ORM relationships -- data isolation enforced at service layer via client_id filtering"
  - "NTFS path validator on Settings to prevent WAL corruption in WSL2"

patterns-established:
  - "TimestampMixin: created_at + updated_at on all models via mapped_column with server_default"
  - "SQLCipher PRAGMA injection: event listener sets WAL, foreign_keys, busy_timeout on every connection"
  - "get_db() context manager: try/yield/finally pattern for session lifecycle"
  - "Encrypted backup via ATTACH + sqlcipher_export instead of sqlite3 online backup API"
  - "Three-part exception hierarchy: message + detail + suggestion"

requirements-completed: [SAFE-02, SAFE-01, CLNT-01, CLNT-02, CLNT-03, CLNT-04, CLNT-05, CLNT-06, CLNT-07, CLNT-08]

# Metrics
duration: 5min
completed: 2026-02-27
---

# Phase 1 Plan 1: Database Foundation Summary

**SQLCipher-encrypted SQLAlchemy engine with 6 ORM models, Pydantic schemas, Alembic migration pipeline, and encrypted backup utility**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-27T04:28:35Z
- **Completed:** 2026-02-27T04:33:59Z
- **Tasks:** 3
- **Files modified:** 20

## Accomplishments
- Python package `sophia` initialized with all Phase 1 dependencies via uv
- SQLCipher-encrypted engine factory with automatic PRAGMA key injection, WAL mode, and foreign key enforcement
- All 6 ORM models mapped to tables: clients, voice_profiles, voice_materials, enrichment_log, audit_log, institutional_knowledge
- Pydantic v2 schemas for all CRUD operations with input validation and response serialization
- Alembic migration pipeline using the application's SQLCipher engine (no hardcoded URL)
- Encrypted backup utility using SQLCipher's ATTACH + sqlcipher_export pattern
- NTFS path validation prevents WAL corruption in WSL2

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffolding, dependencies, and configuration** - `c416179` (feat)
2. **Task 2: SQLCipher engine, ORM models, Pydantic schemas, and backup utility** - `39db578` (feat)
3. **Task 3: Alembic migration pipeline and initial migration** - `6761806` (feat)

## Files Created/Modified
- `backend/pyproject.toml` - Package metadata and all Phase 1 dependencies
- `backend/src/sophia/__init__.py` - Package version string
- `backend/src/sophia/config.py` - Pydantic Settings with SecretStr encryption key and NTFS validator
- `backend/src/sophia/exceptions.py` - Exception hierarchy with message/detail/suggestion structure
- `backend/src/sophia/db/__init__.py` - Database layer exports
- `backend/src/sophia/db/engine.py` - SQLCipher engine factory, SessionLocal, get_db context manager
- `backend/src/sophia/db/base.py` - DeclarativeBase and TimestampMixin
- `backend/src/sophia/db/backup.py` - Encrypted backup with rotation via ATTACH + sqlcipher_export
- `backend/src/sophia/intelligence/__init__.py` - Intelligence module init
- `backend/src/sophia/intelligence/models.py` - Client, VoiceProfile, VoiceMaterial, EnrichmentLog, AuditLog models
- `backend/src/sophia/intelligence/schemas.py` - Pydantic schemas for all intelligence models
- `backend/src/sophia/institutional/__init__.py` - Institutional module init
- `backend/src/sophia/institutional/models.py` - InstitutionalKnowledge model (no FK to clients)
- `backend/alembic.ini` - Alembic config (no hardcoded sqlalchemy.url)
- `backend/alembic/env.py` - Uses application's SQLCipher engine for migrations
- `backend/alembic/script.py.mako` - Migration template
- `backend/alembic/versions/001_initial_schema.py` - Initial schema with all 6 tables
- `.env.example` - Environment variable template

## Decisions Made
- Used `get_settings()` factory function instead of module-level `settings` singleton to avoid import-time .env file requirement -- allows test environments to set env vars before importing
- Synchronous SQLAlchemy engine (not async) because sqlcipher3 has no async driver and the single-operator architecture gains nothing from async DB access
- JSON columns for voice profiles, onboarding state, guardrails, and other evolving structures to avoid migrations when dimensions change
- No cross-client ORM relationships to enforce SAFE-01 data isolation at the model level
- NTFS path rejection via model_validator to prevent WAL corruption when running on WSL2

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used get_settings() factory instead of module-level singleton**
- **Found during:** Task 1 (config.py creation)
- **Issue:** Plan specified `settings = Settings()` as a module-level singleton, but this fails at import time when .env is missing or env vars aren't set (e.g., during testing or in the engine module which imports config)
- **Fix:** Created `get_settings()` factory function that constructs Settings on demand, allowing env vars to be set before the first call
- **Files modified:** backend/src/sophia/config.py
- **Verification:** Config imports cleanly without requiring .env at import time
- **Committed in:** c416179 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for testability and clean import chain. No scope creep.

## Issues Encountered
None -- all dependencies installed cleanly, SQLCipher encryption verified working, Alembic migrations ran successfully.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Database foundation complete, ready for service layer development (Plan 01-02)
- All ORM models are stable contracts for Plans 01-02 and 01-03 to build against
- Alembic pipeline ready for future schema changes
- Configuration management handles encryption keys securely

## Self-Check: PASSED

All 12 key files verified present on disk. All 3 task commits (c416179, 39db578, 6761806) verified in git log.

---
*Phase: 01-client-foundation-data-security*
*Completed: 2026-02-27*
