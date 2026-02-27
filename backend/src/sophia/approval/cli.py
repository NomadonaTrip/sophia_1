"""Minimal Sprint 0 CLI for content approval.

Provides an interactive terminal interface for the operator to review,
approve, reject, edit, and skip content drafts. Calls the same approval
service functions as the REST router for consistency.

Usage:
    from sophia.approval.cli import run_approval_cli
    from sophia.db.engine import SessionLocal
    run_approval_cli(SessionLocal)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sophia.approval.service import (
    approve_draft,
    edit_draft,
    get_approval_queue,
    reject_draft,
    skip_draft,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


def run_approval_cli(db_session_factory: sessionmaker) -> None:
    """Interactive approval CLI.

    Lists pending in_review drafts and accepts commands:
    approve N, reject N, edit N, skip N, quit
    """
    print("\n=== Sophia Approval CLI (Sprint 0) ===\n")

    while True:
        db = db_session_factory()
        try:
            drafts = get_approval_queue(db)

            if not drafts:
                print("No drafts awaiting review.")
                print("Type 'quit' to exit or press Enter to refresh.\n")
                cmd = input("> ").strip().lower()
                if cmd == "quit":
                    break
                continue

            # Display drafts
            print(f"\n{'='*60}")
            print(f"{'#':>3}  {'Client':>8}  {'Platform':<10}  {'Voice%':>6}  Copy Preview")
            print(f"{'='*60}")
            for i, draft in enumerate(drafts, 1):
                copy_preview = draft.copy[:80].replace("\n", " ")
                voice_pct = (
                    f"{draft.voice_confidence_pct:.0f}%"
                    if draft.voice_confidence_pct is not None
                    else "  --"
                )
                print(
                    f"[{i:>2}]  {draft.client_id:>8}  "
                    f"{draft.platform:<10}  {voice_pct:>6}  {copy_preview}"
                )
            print()

            cmd = input("Command (approve N / reject N / edit N / skip N / quit): ").strip()

            if cmd.lower() == "quit":
                break

            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                print("Usage: approve N | reject N | edit N | skip N | quit")
                continue

            action, num_str = parts[0].lower(), parts[1]
            try:
                idx = int(num_str) - 1
                if idx < 0 or idx >= len(drafts):
                    print(f"Invalid number. Choose 1-{len(drafts)}.")
                    continue
            except ValueError:
                print("Invalid number.")
                continue

            draft = drafts[idx]

            if action == "approve":
                mode = input("Publish mode (auto/manual) [auto]: ").strip() or "auto"
                result = approve_draft(db, draft.id, publish_mode=mode, actor="operator:cli")
                db.commit()
                print(f"  Approved: draft #{result.id} -> {result.status} ({mode})")

            elif action == "reject":
                guidance = input("Guidance (optional): ").strip() or None
                tags_raw = input("Tags (comma-separated, optional): ").strip()
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()] or None
                result = reject_draft(db, draft.id, tags=tags, guidance=guidance, actor="operator:cli")
                db.commit()
                print(f"  Rejected: draft #{result.id}")

            elif action == "edit":
                print(f"  Current copy: {draft.copy[:200]}")
                new_copy = input("  New copy: ").strip()
                if not new_copy:
                    print("  Edit cancelled (empty input).")
                    continue
                result = edit_draft(db, draft.id, new_copy=new_copy, actor="operator:cli")
                db.commit()
                print(f"  Edited & approved: draft #{result.id}")

            elif action == "skip":
                result = skip_draft(db, draft.id, actor="operator:cli")
                db.commit()
                print(f"  Skipped: draft #{result.id}")

            else:
                print(f"Unknown command: {action}")

        except Exception as e:
            print(f"Error: {e}")
            db.rollback()
        finally:
            db.close()

    print("\nGoodbye.")
